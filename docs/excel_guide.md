# Excel workbook guide

File: [`excel/Datos-Caso-Final.xlsx`](../excel/Datos-Caso-Final.xlsx), sheet `Hoja1`. Formulas are listed with the English function names under which they are stored in the file (a Spanish-language Excel shows them as `PROMEDIO`, `DESVEST.M`, `COVARIANZA.M`). Solver's weights and results are values, not formulas, except where indicated.

## 1. Data and returns

| Cells | Content | Formula / source |
|---|---|---|
| `A1:E506` | Date and closing prices of AAPL (header "APPL"), MSFT, AMZN and the S&P 500 | Yahoo Finance. Descending order: row 2 is 1/9/2021 and row 506 is 3/9/2019. |
| `M2:P2` | Return headers | |
| `M3:P506` | 504 daily arithmetic returns | `=B2/B3-1` (each price divided by the one in the row below, which is the previous day) |

## 2. Individual statistics (Phase A)

| Cells | Content | Formula |
|---|---|---|
| `T2:W2` | Mean daily return | `=AVERAGE(M3:M506)` |
| `T3:W3` | Daily volatility | `=STDEV.S(M3:M506)` |
| `T5:W5` | Annual return | `=(1+T2)^252-1` |
| `T6:W6` | Annual volatility | `=SQRT(252)*T3` |

## 3. Covariances and portfolio (Phase B)

| Cells | Content | Formula |
|---|---|---|
| `Z2:AB7` | Pairwise covariances, daily (`AA`) and annual (`AB`) | `=COVARIANCE.S(M3:M506,N3:N506)` and `=AA2*252` |
| `AD2:AH6` | Annualised variance-covariance matrix (the 3-stock part is `AE3:AG5`) | `=COVARIANCE.S(INDEX(...),INDEX(...))*252` |
| `AE10:AG10` | Minimum-variance portfolio weights | Solver's changing cells |
| `AF14` | Portfolio return | `=SUMPRODUCT(T5:V5,AE10:AG10)` |
| `AF15` | Portfolio risk (matrix formula) | `=SQRT(MMULT(MMULT(AE10:AG10,AE3:AG5),TRANSPOSE(AE10:AG10)))` |
| `AF16` | Sum of weights | `=SUM(AE10:AG10)` |
| `AG14`, `AG15` | Vertex return and risk | **Pasted values** (copied from `AF14` and `AF15`) |

### Solver configuration saved in the workbook

- Objective: minimise `AF15`.
- Variables: `AE10:AG10`.
- Constraints: `AF16 = 1` and `AF14 = AK7` (target return), plus non-negativity.
- Method: GRG Nonlinear.

The constraint `AF14 = AK7` is the one from the last saved run, which reproduces the vertex. For each frontier point, the target value is changed and Solver is run again.

## 4. Efficient frontier

| Cells | Content |
|---|---|
| `AK3:AK15` | Target returns of the 13 points |
| `AL3:AL15` | Minimum risk for each target return (**pasted values** from Solver) |
| `AK3`, `AK15` | Return of 100% AMZN and of 100% AAPL |
| `AK7`, `AL7` | Vertex (linked to `AG14` and `AG15`) |
| `AN3` | Step from the minimum to the vertex: `=(AK7-AK3)/4` |
| `AO3` | Step from the vertex to the maximum: `=(AK15-AK7)/8` |

## 5. CAPM (Phase C)

| Cells | Content |
|---|---|
| `H3:K3` | Betas of AAPL, MSFT, AMZN and the S&P 500 (1.15, 1.12, 0.72, 1.00) |
| `H5` | Risk-free rate (0.0131) |
| `H7:K7` | CAPM return: `=$H$5+H3*($W$5-$H$5)` |

## 6. CML and projection (Phase D)

| Cells | Content | Formula |
|---|---|---|
| `H26` | Market Sharpe ratio | `=(W5-H5)/W6` |
| `G29:H29` | Mixed portfolio weights (risk-free asset / S&P 500) | 0.5 and 0.5 |
| `G30` | Mixed portfolio return | `=G29*H5+H29*W5` |
| `H30` | Mixed portfolio risk | `=(G30-H5)/H26` |
| `J29:K30` | S&P 500 point on the CML | |
| `H32`, `H33` | Horizon (10 years) and capital (2,000,000) | |
| `H34` | Future value | `=H33*(1+G30)^H32` |

## 7. Charts in the workbook

| Chart | X axis | Y axis |
|---|---|---|
| Risk vs. return | `T6:W6` | `T5:W5` |
| Efficient frontier | `AL3:AL15` | `AK3:AK15` |
| Security Market Line | `H3:K3` | `H7:K7` |
