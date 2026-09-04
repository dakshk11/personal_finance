export const PRODUCT_NAME = "FinanceOS";
export const PRODUCT_MARK = "F";
export const PRODUCT_TAGLINE = "Personal finance command center for planning, portfolios, and market research.";

/** Which horizon a destination serves. Chosen on the home page and remembered per browser. */
export type Lane = "trade" | "invest";

export const LANE_STORAGE_KEY = "financeos.lane";

export type NavItem = { href: string; label: string; lane?: Lane };

export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Home" },
  { href: "/studio", label: "Studio", lane: "trade" },
  { href: "/dashboard", label: "Dashboard", lane: "invest" },
  { href: "/retirement-analyzer", label: "Plan", lane: "invest" },
  { href: "/portfolio", label: "Portfolio", lane: "invest" },
  { href: "/diversify", label: "Diversify", lane: "invest" },
  { href: "/research", label: "Research", lane: "invest" }
];

/** Home stays first; the remembered lane's destinations come next. */
export function orderNavForLane(items: NavItem[], lane: Lane | null): NavItem[] {
  if (!lane) return items;
  const rank = (item: NavItem) => (!item.lane ? 0 : item.lane === lane ? 1 : 2);
  return [...items].sort((a, b) => rank(a) - rank(b));
}

export function readStoredLane(): Lane | null {
  try {
    const value = window.localStorage.getItem(LANE_STORAGE_KEY);
    return value === "trade" || value === "invest" ? value : null;
  } catch {
    return null;
  }
}

export function storeLane(lane: Lane) {
  try {
    window.localStorage.setItem(LANE_STORAGE_KEY, lane);
  } catch {
    /* private mode or blocked storage: the choice just isn't remembered */
  }
}
