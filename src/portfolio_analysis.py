#!/usr/bin/env python3
"""
Portfolio analysis: Markowitz, CAPM, CML and wealth projection.

Replicates in Python the calculations of the Excel workbook
``excel/Datos-Caso-Final.xlsx`` (case study "Manuela's new responsibilities and
her investment decision in the capital markets"):

    A. Annualised expected return and volatility of AAPL, MSFT, AMZN and the S&P 500.
    B. Variance-covariance matrix, minimum-variance portfolio (no short selling)
       and a 13-point efficient frontier.
    C. CAPM and the Security Market Line (SML).
    D. Capital Market Line (CML), 50/50 allocation and future value of the wealth.

Prices and parameters (risk-free rate, betas, capital, horizon, CML weights) are
read from the workbook itself. At the end, the script compares its results with
the values Excel calculated and saves the detail in ``data/``.

Usage (from any folder):
    python src/portfolio_analysis.py
    python src/portfolio_analysis.py --excel path/to/workbook.xlsx --show
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

if "--show" not in sys.argv:
    matplotlib.use("Agg")  # no-window backend: images are only saved to disk
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
import pandas as pd
from scipy.optimize import minimize

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
TRADING_DAYS = 252                      # annualisation convention
SHEET = "Hoja1"                         # worksheet name in the Excel workbook
STOCKS = ["AAPL", "MSFT", "AMZN"]       # optimisation universe
ASSETS = STOCKS + ["S&P500"]            # S&P 500 = market portfolio
N_FRONTIER_LOW, N_FRONTIER_HIGH = 4, 8  # frontier segments (4 + 8 = 13 points)

ROOT = Path(__file__).resolve().parents[1]

# Colour-blind-friendly palette (Okabe-Ito)
COLORS = {"AAPL": "#0072B2", "MSFT": "#009E73", "AMZN": "#E69F00", "S&P500": "#555555",
          "line": "#CC79A7", "gmv": "#D55E00"}


@dataclass
class Inputs:
    """Parameters that the Excel workbook holds as input data."""
    rf: float                 # risk-free rate (10-year Treasury, 01/09/2021)
    betas: pd.Series          # betas of AAPL, MSFT, AMZN and the S&P 500
    w_rf: float               # weight in the risk-free asset (mixed portfolio)
    w_mkt: float              # weight in the S&P 500 (mixed portfolio)
    years: float              # projection horizon
    capital: float            # initial capital (USD)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def load_prices(path: Path) -> pd.DataFrame:
    """Read the closing prices (columns A:E) and sort them chronologically."""
    raw = pd.read_excel(path, sheet_name=SHEET, usecols="A:E").dropna(how="all")
    raw = raw.rename(columns={"APPL": "AAPL"})  # the workbook header reads "APPL"
    raw["Date"] = pd.to_datetime(raw["Date"], format="%b %d, %Y")
    prices = raw.set_index("Date").sort_index()[ASSETS].astype(float)
    if prices.isna().any().any():
        raise ValueError("The workbook contains empty prices.")
    return prices


def load_inputs(path: Path) -> Inputs:
    """Read the input parameters (cells H3:K3, H5, G29:H29, H32, H33)."""
    ws = openpyxl.load_workbook(path, data_only=True)[SHEET]
    betas = pd.Series([ws[c].value for c in ("H3", "I3", "J3", "K3")], index=ASSETS)
    return Inputs(rf=float(ws["H5"].value), betas=betas,
                  w_rf=float(ws["G29"].value), w_mkt=float(ws["H29"].value),
                  years=float(ws["H32"].value), capital=float(ws["H33"].value))


# --------------------------------------------------------------------------- #
# Phase A: individual risk and return
# --------------------------------------------------------------------------- #
def arithmetic_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """R_t = P_t / P_{t-1} - 1."""
    return prices.pct_change().dropna()


def asset_statistics(returns: pd.DataFrame) -> pd.DataFrame:
    """Daily mean and standard deviation; compounded annual return and annual volatility."""
    mean_d = returns.mean()                      # AVERAGE
    std_d = returns.std(ddof=1)                  # STDEV.S
    return pd.DataFrame({
        "daily_return": mean_d,
        "daily_vol": std_d,
        "annual_return": (1 + mean_d) ** TRADING_DAYS - 1,
        "annual_vol": std_d * np.sqrt(TRADING_DAYS),
    })


# --------------------------------------------------------------------------- #
# Phase B: Markowitz
# --------------------------------------------------------------------------- #
def annual_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Daily sample covariance (COVARIANCE.S) x 252."""
    return returns.cov(ddof=1) * TRADING_DAYS


def portfolio_vol(w: np.ndarray, cov: np.ndarray) -> float:
    """sigma_p = sqrt(w' Sigma w)."""
    return float(np.sqrt(w @ cov @ w))


def _solve(cov: np.ndarray, extra_constraints: list[dict]) -> np.ndarray:
    """Minimise variance subject to sum(w) = 1 and w >= 0 (plus any extra constraints)."""
    n = cov.shape[0]
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}] + extra_constraints
    res = minimize(lambda w: w @ cov @ w, x0=np.full(n, 1.0 / n), method="SLSQP",
                   jac=lambda w: 2 * cov @ w, bounds=[(0.0, 1.0)] * n,
                   constraints=constraints, options={"ftol": 1e-15, "maxiter": 1000})
    if not res.success:
        raise RuntimeError(f"The optimisation did not converge: {res.message}")
    return np.clip(res.x, 0.0, 1.0)


def min_variance_portfolio(cov: np.ndarray) -> np.ndarray:
    """Minimum-variance weights, no short selling."""
    return _solve(cov, [])


def efficient_frontier(mu: np.ndarray, cov: np.ndarray) -> pd.DataFrame:
    """13 minimum-variance portfolios for increasing target returns.

    Replicates the Excel workbook: 4 equal steps from the lowest return (100 % AMZN)
    to the minimum-variance portfolio, then 8 equal steps up to the highest return
    (100 % AAPL). Each point minimises risk for its target return.
    """
    w_gmv = min_variance_portfolio(cov)
    r_gmv = float(w_gmv @ mu)
    targets = np.r_[np.linspace(mu.min(), r_gmv, N_FRONTIER_LOW + 1),
                    np.linspace(r_gmv, mu.max(), N_FRONTIER_HIGH + 1)[1:]]
    rows = []
    for target in targets:
        cons = [{"type": "eq", "fun": lambda w, t=target: w @ mu - t}]
        w = _solve(cov, cons)
        rows.append({"ret": float(w @ mu), "vol": portfolio_vol(w, cov),
                     **dict(zip(STOCKS, w))})
    frontier = pd.DataFrame(rows)
    # Below the vertex's return the curve is the inefficient (dominated) branch.
    frontier["efficient"] = frontier["ret"] >= r_gmv - 1e-9
    return frontier


# --------------------------------------------------------------------------- #
# Phases C and D: CAPM, CML and projection
# --------------------------------------------------------------------------- #
def capm_returns(inp: Inputs, market_return: float) -> pd.Series:
    """E(R_i) = Rf + beta_i (Rm - Rf)."""
    return inp.rf + inp.betas * (market_return - inp.rf)


def capital_market_line(inp: Inputs, market_return: float, market_vol: float) -> dict:
    """Market Sharpe ratio, mixed portfolio on the CML and future value."""
    sharpe = (market_return - inp.rf) / market_vol
    ret_p = inp.w_rf * inp.rf + inp.w_mkt * market_return
    vol_p = (ret_p - inp.rf) / sharpe                 # solved from the CML
    fv = inp.capital * (1 + ret_p) ** inp.years
    return {"market_sharpe": sharpe, "portfolio_return": ret_p,
            "portfolio_vol": vol_p, "future_value": fv}


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _style() -> None:
    plt.rcParams.update({
        "figure.dpi": 100, "savefig.dpi": 200, "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "axes.titleweight": "bold",
    })


def _pct_axes(ax) -> None:
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))


def plot_risk_return(stats: pd.DataFrame, out: Path) -> None:
    """Chart 1: risk (X) vs. expected annual return (Y)."""
    fig, ax = plt.subplots(figsize=(7, 4.8))
    for name in ASSETS:
        x, y = stats.loc[name, "annual_vol"], stats.loc[name, "annual_return"]
        ax.scatter(x, y, s=90, color=COLORS[name], zorder=3)
        ax.annotate(f"{name}\n({x:.1%}; {y:.1%})", (x, y), textcoords="offset points",
                    xytext=(10, -4), fontsize=9)
    ax.set(title="Risk vs. expected annual return",
           xlabel="Risk (annual volatility)", ylabel="Expected annual return",
           xlim=(0.23, 0.42), ylim=(0.2, 0.95))
    ax.xaxis.set_major_locator(plt.MultipleLocator(0.05))
    _pct_axes(ax)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_frontier(frontier: pd.DataFrame, stats: pd.DataFrame, out: Path) -> None:
    """Chart 2: Markowitz frontier (13 portfolios)."""
    fig, ax = plt.subplots(figsize=(7.5, 5))
    eff = frontier[frontier["efficient"]]
    ineff = frontier[~frontier["efficient"]]
    gmv = frontier.loc[frontier["vol"].idxmin()]
    # The inefficient branch is joined to the vertex so that the curve is continuous.
    ax.plot(pd.concat([ineff, gmv.to_frame().T])["vol"],
            pd.concat([ineff, gmv.to_frame().T])["ret"],
            "--", color="#999999", marker="o", ms=4, label="Inefficient segment (dominated)")
    ax.plot(eff["vol"], eff["ret"], "-", color=COLORS["line"], marker="o", ms=5,
            lw=2, label="Efficient frontier")
    ax.scatter(gmv["vol"], gmv["ret"], marker="*", s=240, color=COLORS["gmv"], zorder=4,
               label=f"Minimum variance ({gmv['vol']:.2%}; {gmv['ret']:.2%})")
    for name in STOCKS:
        x, y = stats.loc[name, "annual_vol"], stats.loc[name, "annual_return"]
        ax.scatter(x, y, s=70, color=COLORS[name], zorder=3, edgecolor="white")
        ax.annotate(name, (x, y), textcoords="offset points", xytext=(7, -3), fontsize=9)
    ax.set(title="Markowitz efficient frontier (AAPL, MSFT, AMZN)",
           xlabel="Risk (annual volatility)", ylabel="Expected annual return")
    _pct_axes(ax)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_sml(capm: pd.Series, inp: Inputs, market_return: float, out: Path) -> None:
    """Chart 3: Security Market Line (beta vs. CAPM return)."""
    fig, ax = plt.subplots(figsize=(7, 4.8))
    beta_grid = np.linspace(0, 1.3, 50)
    ax.plot(beta_grid, inp.rf + beta_grid * (market_return - inp.rf),
            color=COLORS["line"], lw=2, label="SML")
    # Label offset (points) and alignment for each asset, so that labels do not overlap.
    offsets = {"AAPL": ((-10, 16), "right"), "MSFT": ((12, -30), "left"),
               "AMZN": ((12, -30), "left"), "S&P500": ((12, -30), "left")}
    for name in ASSETS:
        x, y = inp.betas[name], capm[name]
        ax.scatter(x, y, s=90, color=COLORS[name], zorder=3)
        (dx, dy), ha = offsets[name]
        ax.annotate(f"{name}\n(β={x:.2f}; {y:.2%})", (x, y), textcoords="offset points",
                    xytext=(dx, dy), ha=ha, fontsize=9)
    ax.scatter(0, inp.rf, color="black", s=40, zorder=3)
    ax.annotate(f"Rf = {inp.rf:.2%}", (0, inp.rf), textcoords="offset points",
                xytext=(14, -14), fontsize=9)
    ax.set(title="Security Market Line (CAPM)", xlabel="Beta (β)",
           ylabel="Expected return (CAPM)", xlim=(-0.02, 1.4), ylim=(-0.03, 0.40))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Verification against the values calculated by Excel
# --------------------------------------------------------------------------- #
def verify_against_excel(path: Path, res: dict) -> pd.DataFrame:
    """Compare each Python result with the corresponding workbook cell."""
    ws = openpyxl.load_workbook(path, data_only=True)[SHEET]
    rows: list[tuple[str, str, float, float]] = []

    def add(label: str, cell: str, python_value: float) -> None:
        rows.append((label, cell, float(ws[cell].value), float(python_value)))

    stats, cov, w = res["stats"], res["cov4"], res["w_gmv"]
    for col, name in zip("TUVW", ASSETS):
        add(f"Annual return {name}", f"{col}5", stats.loc[name, "annual_return"])
        add(f"Annual volatility {name}", f"{col}6", stats.loc[name, "annual_vol"])
    cov_cols = ["AE", "AF", "AG", "AH"]  # covariance matrix AE3:AH6
    for i, row_name in enumerate(ASSETS):
        for j, col_name in enumerate(ASSETS):
            add(f"Annual covariance {row_name}-{col_name}", f"{cov_cols[j]}{3 + i}",
                cov.loc[row_name, col_name])
    for col, name, wi in zip(["AE", "AF", "AG"], STOCKS, w):
        add(f"Minimum-variance weight {name}", f"{col}10", wi)
    add("Minimum-variance portfolio return", "AG14", res["ret_gmv"])
    add("Minimum-variance portfolio volatility", "AG15", res["vol_gmv"])
    for col, name in zip("HIJK", ASSETS):
        add(f"CAPM return {name}", f"{col}7", res["capm"][name])
    add("Market Sharpe ratio", "H26", res["cml"]["market_sharpe"])
    add("50/50 portfolio return", "G30", res["cml"]["portfolio_return"])
    add("50/50 portfolio volatility", "H30", res["cml"]["portfolio_vol"])
    add("Future value (USD)", "H34", res["cml"]["future_value"])
    for k, (_, fr) in enumerate(res["frontier"].iterrows()):
        add(f"Frontier point {k + 1}: return", f"AK{3 + k}", fr["ret"])
        add(f"Frontier point {k + 1}: risk", f"AL{3 + k}", fr["vol"])

    out = pd.DataFrame(rows, columns=["item", "excel_cell", "excel", "python"])
    out["abs_diff"] = (out["excel"] - out["python"]).abs()
    return out


# --------------------------------------------------------------------------- #
# Main program
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--excel", type=Path, default=ROOT / "excel" / "Datos-Caso-Final.xlsx")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--images-dir", type=Path, default=ROOT / "images")
    ap.add_argument("--show", action="store_true", help="show the charts on screen")
    args = ap.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.images_dir.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.float_format", lambda v: f"{v:,.6f}")

    # --- Data ---------------------------------------------------------------
    prices = load_prices(args.excel)
    inp = load_inputs(args.excel)
    returns = arithmetic_returns(prices)
    print(f"Prices: {len(prices)} observations "
          f"({prices.index.min():%d/%m/%Y} - {prices.index.max():%d/%m/%Y}); "
          f"returns: {len(returns)}")

    # --- Phase A ------------------------------------------------------------
    stats = asset_statistics(returns)
    print("\n== Phase A: individual risk and return ==")
    print(stats[["annual_return", "annual_vol"]])

    # --- Phase B ------------------------------------------------------------
    cov4 = annual_covariance(returns)
    cov = cov4.loc[STOCKS, STOCKS].to_numpy()
    mu = stats.loc[STOCKS, "annual_return"].to_numpy()
    w_gmv = min_variance_portfolio(cov)
    ret_gmv, vol_gmv = float(w_gmv @ mu), portfolio_vol(w_gmv, cov)
    frontier = efficient_frontier(mu, cov)
    print("\n== Phase B: Markowitz ==")
    print(cov4.loc[STOCKS, STOCKS])
    print("Minimum-variance weights: "
          + " | ".join(f"{n} {wi:.2%}" for n, wi in zip(STOCKS, w_gmv)))
    print(f"Return = {ret_gmv:.2%} | Volatility = {vol_gmv:.2%}")

    # --- Phase C ------------------------------------------------------------
    rm, sm = stats.loc["S&P500", "annual_return"], stats.loc["S&P500", "annual_vol"]
    capm = capm_returns(inp, rm)
    print("\n== Phase C: CAPM ==")
    for name in ASSETS:
        print(f"{name:7s} beta = {inp.betas[name]:.2f}  ->  E(R) = {capm[name]:.2%}")

    # --- Phase D ------------------------------------------------------------
    cml = capital_market_line(inp, rm, sm)
    print("\n== Phase D: CML and projection ==")
    print(f"Market Sharpe ratio = {cml['market_sharpe']:.4f}")
    print(f"{inp.w_rf:.0%} risk-free / {inp.w_mkt:.0%} S&P 500 portfolio: "
          f"return = {cml['portfolio_return']:.2%}, volatility = {cml['portfolio_vol']:.2%}")
    print(f"Future value after {inp.years:.0f} years: USD {cml['future_value']:,.2f}")

    # --- Export results -----------------------------------------------------
    stats.to_csv(args.data_dir / "asset_results.csv", index_label="asset")
    cov4.to_csv(args.data_dir / "annual_covariance_matrix.csv", index_label="asset")
    frontier.to_csv(args.data_dir / "efficient_frontier.csv", index_label="point")
    capm_df = pd.DataFrame({"beta": inp.betas, "capm": capm,
                            "historical_return": stats["annual_return"]})
    capm_df["historical_minus_capm"] = capm_df["historical_return"] - capm_df["capm"]
    capm_df.to_csv(args.data_dir / "capm.csv", index_label="asset")
    pd.Series({**{f"w_{n}": w for n, w in zip(STOCKS, w_gmv)},
               "return": ret_gmv, "volatility": vol_gmv}
              ).to_csv(args.data_dir / "min_variance_portfolio.csv", header=["value"],
                       index_label="item")
    pd.Series(cml).to_csv(args.data_dir / "cml_projection.csv", header=["value"],
                          index_label="item")

    # --- Charts -------------------------------------------------------------
    _style()
    plot_risk_return(stats, args.images_dir / "01_risk_return.png")
    plot_frontier(frontier, stats, args.images_dir / "02_efficient_frontier.png")
    plot_sml(capm, inp, rm, args.images_dir / "03_sml_capm.png")
    if args.show:
        plt.show()

    # --- Verification against Excel ----------------------------------------
    check = verify_against_excel(args.excel, {
        "stats": stats, "cov4": cov4, "w_gmv": w_gmv, "ret_gmv": ret_gmv,
        "vol_gmv": vol_gmv, "capm": capm, "cml": cml, "frontier": frontier})
    check.to_csv(args.data_dir / "excel_vs_python_verification.csv", index=False)
    print(f"\n== Verification, Excel vs. Python ({len(check)} values) ==")
    print(f"Maximum absolute difference: {check['abs_diff'].max():.3e}")
    print("Five largest differences:")
    for _, r in check.nlargest(5, "abs_diff").iterrows():
        print(f"  {r['item']:<45s} Excel {r['excel']:>14,.6f}  "
              f"Python {r['python']:>14,.6f}  diff {r['abs_diff']:.2e}")
    print(f"\nResults saved in {args.data_dir}, charts in {args.images_dir}")


if __name__ == "__main__":
    main()
