import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const files = {
  breakout: readFileSync(join(root, "components", "BreakoutScannerTool.tsx"), "utf8"),
  composite: readFileSync(join(root, "components", "CompositeSignalTool.tsx"), "utf8"),
  optitrade: readFileSync(join(root, "components", "OptiTradeLabTool.tsx"), "utf8"),
  wheel: readFileSync(join(root, "components", "WheelScannerTool.tsx"), "utf8"),
};

const checks = [
  ["Breakout default IBKR backend URL", files.breakout, "http://localhost:8002"],
  ["Breakout status endpoint", files.breakout, "/api/breakout/status"],
  ["Breakout scan endpoint", files.breakout, "/api/breakout/scan?"],
  ["Breakout IBKR scan source", files.breakout, 'source: "ibkr"'],
  ["Breakout Nasdaq 100 index parameter", files.breakout, 'index: "ndx100"'],
  ["Breakout run-scan IBKR branch", files.breakout, 'if (dataSource === "ibkr")'],
  ["Breakout run-scan IBKR call", files.breakout, "return loadIbkrScan()"],
  ["Breakout Yahoo Finance scan endpoint", files.breakout, "/breakout-scanner/scan"],
  ["Breakout IBKR tab label", files.breakout, "IBKR Live · Nasdaq-100"],
  ["Breakout Yahoo tab label", files.breakout, "Yahoo Finance · S&P 500"],
  ["Composite default IBKR backend URL", files.composite, "http://localhost:8002"],
  ["Composite signal endpoint", files.composite, "/api/composite-signal"],
  ["Composite quote endpoint", files.composite, "/api/quotes?symbols="],
  ["OptiTrade default IBKR backend URL", files.optitrade, "http://localhost:8002"],
  ["OptiTrade signal endpoint", files.optitrade, "/api/optitrade-lab/signals?symbols="],
  ["OptiTrade backtest endpoint", files.optitrade, "/api/optitrade-lab/backtest?"],
  ["Wheel default IBKR backend URL", files.wheel, "http://localhost:8002"],
  ["Wheel status endpoint", files.wheel, "/api/status"],
  ["Wheel watchlist endpoint", files.wheel, "/api/watchlist"],
  ["Wheel quotes endpoint", files.wheel, "/api/quotes?symbols="],
  ["Wheel options endpoint", files.wheel, "/api/options/"],
];

const missing = checks.filter(([, source, needle]) => !source.includes(needle));
if (missing.length) {
  console.error("AI Advisor IBKR contract check failed.");
  for (const [label,, needle] of missing) {
    console.error(`- Missing ${label}: ${needle}`);
  }
  process.exit(1);
}

console.log("AI Advisor IBKR contract check passed.");
