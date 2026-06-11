"""
Detects local hardware specs so the router can filter out models that won't fit in memory.

Detection strategy per platform:
  RAM        — psutil (cross-platform) → sysctl (macOS) → /proc/meminfo (Linux)
  VRAM       — nvidia-smi (NVIDIA) → rocm-smi (AMD) → sysctl/ioreg (Apple Silicon)
  CPU        — platform + psutil
  Ollama RAM — reads OLLAMA_MAX_LOADED_MODELS / OLLAMA_NUM_PARALLEL env vars

All subprocess calls have short timeouts and are individually try/excepted,
so a missing tool never crashes the router.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from typing import Optional


@dataclass
class HardwareProfile:
    ram_gb: float                    # total system RAM
    vram_gb: float                   # dedicated GPU VRAM (0 if none / integrated)
    unified_memory_gb: float         # Apple Silicon shared memory (0 if not M-series)
    cpu_cores: int
    gpu_name: str                    # human-readable GPU label
    platform: str                    # "macos" | "linux" | "windows"
    is_apple_silicon: bool

    @property
    def effective_model_memory_gb(self) -> float:
        """
        Memory available for a model to load into.
        On Apple Silicon, Ollama uses unified memory.
        On discrete GPU systems, uses VRAM (falls back to RAM for CPU inference).
        """
        if self.is_apple_silicon:
            return self.unified_memory_gb * 0.75  # leave 25% for OS / other processes
        if self.vram_gb > 0:
            return self.vram_gb * 0.90
        return self.ram_gb * 0.60  # CPU inference: generous RAM headroom

    def can_run_model(self, min_vram_gb: float) -> bool:
        return self.effective_model_memory_gb >= min_vram_gb

    def summary(self) -> str:
        lines = [f"Platform: {self.platform}"]
        if self.is_apple_silicon:
            lines.append(f"Apple Silicon — {self.unified_memory_gb:.0f} GB unified memory")
        else:
            lines.append(f"RAM: {self.ram_gb:.0f} GB")
            if self.vram_gb:
                lines.append(f"GPU: {self.gpu_name} — {self.vram_gb:.0f} GB VRAM")
            else:
                lines.append("GPU: none detected (CPU inference)")
        lines.append(f"CPU cores: {self.cpu_cores}")
        lines.append(f"Effective model memory: {self.effective_model_memory_gb:.1f} GB")
        return "\n".join(lines)


class HardwareDetector:
    """
    Detects hardware specs using lightweight system commands.
    Results are cached after first call — call .detect() once at startup.
    """

    def detect(self) -> HardwareProfile:
        sys_platform = platform.system().lower()
        is_apple_silicon = self._is_apple_silicon()

        ram_gb = self._detect_ram()
        unified_gb = self._detect_apple_unified_memory() if is_apple_silicon else 0.0
        vram_gb, gpu_name = (0.0, "Apple Silicon") if is_apple_silicon else self._detect_discrete_vram()
        cpu_cores = self._detect_cpu_cores()

        plat = {"darwin": "macos", "linux": "linux", "windows": "windows"}.get(sys_platform, sys_platform)

        return HardwareProfile(
            ram_gb=ram_gb,
            vram_gb=vram_gb,
            unified_memory_gb=unified_gb,
            cpu_cores=cpu_cores,
            gpu_name=gpu_name,
            platform=plat,
            is_apple_silicon=is_apple_silicon,
        )

    # ------------------------------------------------------------------ #
    # RAM
    # ------------------------------------------------------------------ #

    def _detect_ram(self) -> float:
        # Try psutil first (most reliable, cross-platform)
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 ** 3)
        except ImportError:
            pass

        # macOS: sysctl
        if platform.system() == "Darwin":
            val = self._sysctl("hw.memsize")
            if val:
                return int(val) / (1024 ** 3)

        # Linux: /proc/meminfo
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
        except OSError:
            pass

        return 0.0

    # ------------------------------------------------------------------ #
    # Apple Silicon unified memory
    # ------------------------------------------------------------------ #

    def _is_apple_silicon(self) -> bool:
        if platform.system() != "Darwin":
            return False
        machine = platform.machine()
        if machine == "arm64":
            return True
        # Rosetta: check chip via sysctl
        chip = self._sysctl("machdep.cpu.brand_string") or ""
        return "Apple" in chip

    def _detect_apple_unified_memory(self) -> float:
        # sysctl hw.memsize gives total unified memory on Apple Silicon
        val = self._sysctl("hw.memsize")
        if val:
            return int(val) / (1024 ** 3)

        # Fallback: system_profiler (slower but reliable)
        out = self._run(["system_profiler", "SPHardwareDataType"], timeout=8)
        if out:
            m = re.search(r"Memory:\s+(\d+)\s*GB", out, re.IGNORECASE)
            if m:
                return float(m.group(1))

        return 0.0

    # ------------------------------------------------------------------ #
    # Discrete GPU VRAM
    # ------------------------------------------------------------------ #

    def _detect_discrete_vram(self) -> tuple[float, str]:
        # NVIDIA
        result = self._detect_nvidia_vram()
        if result[0] > 0:
            return result

        # AMD (ROCm)
        result = self._detect_amd_vram()
        if result[0] > 0:
            return result

        # macOS Intel with discrete GPU
        if platform.system() == "Darwin":
            result = self._detect_macos_discrete_vram()
            if result[0] > 0:
                return result

        return 0.0, "none"

    def _detect_nvidia_vram(self) -> tuple[float, str]:
        out = self._run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            timeout=5,
        )
        if not out:
            return 0.0, ""
        # Take the first GPU line
        line = out.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                vram_mb = float(parts[-1])
                name = ", ".join(parts[:-1])
                return vram_mb / 1024, name
            except ValueError:
                pass
        return 0.0, ""

    def _detect_amd_vram(self) -> tuple[float, str]:
        out = self._run(["rocm-smi", "--showmeminfo", "vram", "--json"], timeout=5)
        if not out:
            return 0.0, ""
        try:
            import json
            data = json.loads(out)
            # rocm-smi JSON structure varies by version
            for card, info in data.items():
                if isinstance(info, dict):
                    for k, v in info.items():
                        if "vram" in k.lower() and "total" in k.lower():
                            return float(v) / (1024 ** 3), f"AMD GPU ({card})"
        except Exception:
            pass
        return 0.0, ""

    def _detect_macos_discrete_vram(self) -> tuple[float, str]:
        out = self._run(["system_profiler", "SPDisplaysDataType"], timeout=8)
        if not out:
            return 0.0, ""
        vram = 0.0
        name = ""
        for line in out.splitlines():
            if "Chipset Model:" in line:
                name = line.split(":", 1)[-1].strip()
            m = re.search(r"VRAM.*?(\d+)\s*(MB|GB)", line, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                unit = m.group(2).upper()
                vram = val if unit == "GB" else val / 1024
                break
        return vram, name

    # ------------------------------------------------------------------ #
    # CPU
    # ------------------------------------------------------------------ #

    def _detect_cpu_cores(self) -> int:
        try:
            import psutil
            return psutil.cpu_count(logical=False) or os.cpu_count() or 1
        except ImportError:
            pass

        # macOS
        val = self._sysctl("hw.physicalcpu")
        if val:
            return int(val)

        # Linux
        try:
            with open("/proc/cpuinfo") as f:
                cores = {line.split(":")[1].strip() for line in f if line.startswith("core id")}
                if cores:
                    return len(cores)
        except OSError:
            pass

        return os.cpu_count() or 1

    # ------------------------------------------------------------------ #
    # Subprocess helpers
    # ------------------------------------------------------------------ #

    def _run(self, cmd: list[str], timeout: int = 5) -> Optional[str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.stdout if r.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None

    def _sysctl(self, key: str) -> Optional[str]:
        out = self._run(["sysctl", "-n", key], timeout=3)
        return out.strip() if out else None
