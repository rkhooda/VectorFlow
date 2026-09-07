"""
app.py - VectorFlow demo UI (Streamlit)
Run:  streamlit run app.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st
import pandas as pd
import numpy as np

from inference import predict, FEATURE_COLS


FEATURE_DEFAULTS = {
    "Tot Fwd Pkts_sum": 1459.41, "Tot Bwd Pkts_sum": 1885.97,
    "TotLen Fwd Pkts_sum": 103488.75, "TotLen Bwd Pkts_sum": 1635409.47,
    "Flow Duration_mean": 16144159.71, "Flow Duration_std": 32744385.79,
    "Flow IAT Mean_mean": 6671282.01, "Dst Port_nunique": 44.61,
    "SYN Flag Cnt_sum": 10.63, "ACK Flag Cnt_sum": 68.23,
    "RST Flag Cnt_sum": 29.29, "FIN Flag Cnt_sum": 1.29,
    "PSH Flag Cnt_sum": 88.09, "flow_count": 233.96,
    "bwd_fwd_pkt_ratio": 0.96,
    "Tot Fwd Pkts_sum_lag1": 2396.5, "Tot Fwd Pkts_sum_lag2": 4034.46,
    "Tot Fwd Pkts_sum_lag3": 4245.13, "Tot Bwd Pkts_sum_lag1": 1893.84,
    "Tot Bwd Pkts_sum_lag2": 1905.25, "Tot Bwd Pkts_sum_lag3": 1906.78,
    "TotLen Fwd Pkts_sum_lag1": 134184.03, "TotLen Fwd Pkts_sum_lag2": 186621.82,
    "TotLen Fwd Pkts_sum_lag3": 193475.94, "TotLen Bwd Pkts_sum_lag1": 1644350.3,
    "TotLen Bwd Pkts_sum_lag2": 1659035.37, "TotLen Bwd Pkts_sum_lag3": 1659864.54,
    "Flow Duration_mean_lag1": 16163851.77, "Flow Duration_mean_lag2": 16168840.88,
    "Flow Duration_mean_lag3": 16178781.08, "Flow Duration_std_lag1": 32754356.22,
    "Flow Duration_std_lag2": 32737307.99, "Flow Duration_std_lag3": 32743504.85,
    "Flow IAT Mean_mean_lag1": 6663442.99, "Flow IAT Mean_mean_lag2": 6653314.74,
    "Flow IAT Mean_mean_lag3": 6653988.79, "Dst Port_nunique_lag1": 44.65,
    "Dst Port_nunique_lag2": 44.7, "Dst Port_nunique_lag3": 44.68,
    "SYN Flag Cnt_sum_lag1": 10.67, "SYN Flag Cnt_sum_lag2": 10.68,
    "SYN Flag Cnt_sum_lag3": 10.68, "ACK Flag Cnt_sum_lag1": 68.32,
    "ACK Flag Cnt_sum_lag2": 68.41, "ACK Flag Cnt_sum_lag3": 68.41,
    "RST Flag Cnt_sum_lag1": 29.37, "RST Flag Cnt_sum_lag2": 29.39,
    "RST Flag Cnt_sum_lag3": 29.38, "FIN Flag Cnt_sum_lag1": 1.29,
    "FIN Flag Cnt_sum_lag2": 1.29, "FIN Flag Cnt_sum_lag3": 1.29,
    "PSH Flag Cnt_sum_lag1": 88.28, "PSH Flag Cnt_sum_lag2": 88.38,
    "PSH Flag Cnt_sum_lag3": 88.46, "flow_count_lag1": 234.4,
    "flow_count_lag2": 234.78, "flow_count_lag3": 234.98,
    "bwd_fwd_pkt_ratio_lag1": 0.96, "bwd_fwd_pkt_ratio_lag2": 0.97,
    "bwd_fwd_pkt_ratio_lag3": 0.97, "Tot Fwd Pkts_sum_delta1": -937.09,
    "Tot Bwd Pkts_sum_delta1": -7.87, "TotLen Fwd Pkts_sum_delta1": -30695.28,
    "TotLen Bwd Pkts_sum_delta1": -8940.83, "Flow Duration_mean_delta1": -19692.06,
    "Flow Duration_std_delta1": -9970.43, "Flow IAT Mean_mean_delta1": 7839.03,
    "Dst Port_nunique_delta1": -0.04, "SYN Flag Cnt_sum_delta1": -0.03,
    "ACK Flag Cnt_sum_delta1": -0.08, "RST Flag Cnt_sum_delta1": -0.08,
    "FIN Flag Cnt_sum_delta1": 0.0, "PSH Flag Cnt_sum_delta1": -0.19,
    "flow_count_delta1": -0.44, "bwd_fwd_pkt_ratio_delta1": 0.0,
}


def show_results(preds: pd.DataFrame):
    """Render prediction results for a single row."""
    xgb_prob = preds.loc[preds["model"] == "XGBoost", "probability"].values[0]
    xgb_attack = preds.loc[preds["model"] == "XGBoost", "attack_predicted"].values[0]

    if xgb_attack:
        st.error("LIKELY ATTACK IN NEXT 120 SECONDS  (XGBoost)")
    else:
        st.success("No imminent attack predicted  (XGBoost)")

    st.markdown("---")
    st.subheader("Attack probability — all models")

    col1, col2, col3 = st.columns(3)
    for col, model_name in zip([col1, col2, col3], ["LogReg", "RandomForest", "XGBoost"]):
        row = preds[preds["model"] == model_name].iloc[0]
        col.metric(
            label=model_name,
            value=f"{row['probability']:.1%}",
            delta="ATTACK" if row["attack_predicted"] else "safe",
            delta_color="inverse",
        )

    chart_data = (
        preds[["model", "probability"]]
        .set_index("model")
    )
    st.bar_chart(chart_data)


def show_batch_results(preds: pd.DataFrame, uploaded_df: pd.DataFrame):
    """Render results for a CSV upload (multiple rows)."""
    st.subheader(f"Results for {preds['row'].nunique()} rows")

    xgb_preds = preds[preds["model"] == "XGBoost"].copy()
    n_attacks = xgb_preds["attack_predicted"].sum()
    n_total   = len(xgb_preds)

    col1, col2 = st.columns(2)
    col1.metric("Windows analysed", n_total)
    col2.metric("Attack alerts (XGBoost)", int(n_attacks),
                delta_color="inverse",
                delta="high" if n_attacks > 0 else "none")

    st.markdown("---")

    pivot = preds.pivot(index="row", columns="model", values="probability")
    pivot.columns = [f"{c} prob" for c in pivot.columns]
    pivot["XGBoost verdict"] = preds[preds["model"] == "XGBoost"]["attack_predicted"].values

    if "window_start" in uploaded_df.columns:
        pivot.insert(0, "window_start", uploaded_df["window_start"].values)

    st.dataframe(pivot.style.format({c: "{:.3f}" for c in pivot.columns
                                     if "prob" in c}), use_container_width=True)

    st.bar_chart(pivot[[c for c in pivot.columns if "prob" in c]])



st.set_page_config(page_title="VectorFlow", page_icon="shield", layout="wide")
st.title("VectorFlow — Network Attack Forecaster")
st.caption("SIH 2026 | PS 26153 | Predicts whether an attack starts within 120 seconds")

mode = st.radio("Input mode", ["Upload CSV", "Manual input"], horizontal=True)
st.markdown("---")


# ── Mode A: CSV upload ────────────────────────────────────────────────────────
if mode == "Upload CSV":
    st.markdown(
        "Upload a CSV with the 75 feature columns. "
        "`window_start` and `Future_Attack_Target` are optional and will be ignored during inference."
    )
    uploaded = st.file_uploader("Choose a CSV file", type="csv")

    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            st.write(f"Loaded {len(df)} rows, {df.shape[1]} columns")

            with st.spinner("Running inference..."):
                preds = predict(df)

            show_batch_results(preds, df)

        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Unexpected error: {e}")


# ── Mode B: Manual input ──────────────────────────────────────────────────────
else:
    st.markdown(
        "Enter values for the 75 features. "
        "Defaults are the training-set means — adjust only the ones you care about."
    )

    base_cols   = FEATURE_COLS[:15]
    lag_cols    = FEATURE_COLS[15:60]
    delta_cols  = FEATURE_COLS[60:]

    input_vals = {}

    with st.expander("Base features (current window)", expanded=True):
        cols = st.columns(3)
        for i, feat in enumerate(base_cols):
            input_vals[feat] = cols[i % 3].number_input(
                feat, value=float(FEATURE_DEFAULTS[feat]), format="%.2f"
            )

    with st.expander("Lag features (previous windows)", expanded=False):
        cols = st.columns(3)
        for i, feat in enumerate(lag_cols):
            input_vals[feat] = cols[i % 3].number_input(
                feat, value=float(FEATURE_DEFAULTS[feat]), format="%.2f"
            )

    with st.expander("Delta features (current − lag1)", expanded=False):
        cols = st.columns(3)
        for i, feat in enumerate(delta_cols):
            input_vals[feat] = cols[i % 3].number_input(
                feat, value=float(FEATURE_DEFAULTS[feat]), format="%.2f"
            )

    if st.button("Run prediction", type="primary"):
        try:
            with st.spinner("Running inference..."):
                preds = predict(input_vals)
            show_results(preds)
        except Exception as e:
            st.error(str(e))
