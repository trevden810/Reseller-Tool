"""Streamlit dashboard — eBay vs AliExpress Reseller Tool.

Run: streamlit run src/reseller_tool/app.py
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from reseller_tool.ebay import search_ebay, search_ebay_sold
from reseller_tool.aliexpress import search_aliexpress
from reseller_tool.analyzer import (
    analyze_opportunities,
    calculate_margin,
    quick_margin_check,
    get_trend_score,
    get_trend_velocity,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Reseller Tool — eBay vs AliExpress",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .profit-positive { color: #00c853; font-weight: bold; }
    .profit-negative { color: #ff1744; font-weight: bold; }
    .score-high { color: #00c853; font-size: 1.4em; font-weight: bold; }
    .score-mid { color: #ffab00; font-size: 1.4em; font-weight: bold; }
    .score-low { color: #ff1744; font-size: 1.4em; font-weight: bold; }
    div[data-testid="stMetric"] {
        background-color: #1e1e2e;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("💰 Reseller Tool")
    st.caption("eBay vs AliExpress — Find profitable dropship opportunities")

    st.divider()
    st.subheader("🔍 Search Settings")

    query = st.text_input(
        "Product keyword",
        placeholder="e.g. pet bandana dog, posture corrector, LED strip",
        help="Enter the product you want to research",
    )

    col1, col2 = st.columns(2)
    with col1:
        min_price = st.number_input("Min eBay price ($)", value=5.0, min_value=0.0, step=1.0)
    with col2:
        max_price = st.number_input("Max eBay price ($)", value=100.0, min_value=1.0, step=5.0)

    ali_max_price = st.number_input(
        "Max AliExpress source price ($)", value=30.0, min_value=0.0, step=1.0,
        help="Filter out expensive source products",
    )

    result_limit = st.slider("Results per platform", 5, 40, 20)

    st.divider()
    st.subheader("⚙️ Analysis Settings")

    min_similarity = st.slider(
        "Match confidence threshold", 0.20, 0.80, 0.40, 0.05,
        help="Lower = more matches (looser). Higher = fewer but more accurate matches.",
    )

    min_ali_orders = st.number_input(
        "Min AliExpress orders", value=0, min_value=0, step=5,
        help="Only show AliExpress products with this many orders (demand validation)",
    )

    min_ali_rating = st.slider(
        "Min AliExpress rating", 0.0, 5.0, 0.0, 0.1,
        help="Filter out low-rated suppliers",
    )

    use_promoted = st.checkbox(
        "Include promoted listing fee (3%)",
        value=False,
        help="Check if you plan to use eBay promoted listings",
    )

    include_trends = st.checkbox(
        "Include Google Trends data",
        value=True,
        help="Adds ~2s but gives demand scoring",
    )

    st.divider()
    search_clicked = st.button("🚀 Analyze Products", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_analyze, tab_margin_calc, tab_trends, tab_sold = st.tabs(
    ["📊 Product Analysis", "🧮 Margin Calculator", "📈 Trends Scout", "✅ Sold Validation"]
)

# ---------------------------------------------------------------------------
# Tab 1: Product Analysis (main)
# ---------------------------------------------------------------------------
with tab_analyze:
    if not search_clicked or not query:
        st.markdown("## How to use")
        st.markdown(
            """
            1. Enter a product keyword in the sidebar
            2. Adjust price filters and settings
            3. Click **Analyze Products**
            4. Review the ranked opportunities table

            The tool will:
            - Search eBay for current listings at your price range
            - Search AliExpress for source products
            - Fuzzy-match products across platforms
            - Calculate real margins after **all** fees (eBay 13.25% + payment 2.9% + per-order)
            - Score each opportunity 0-100 based on margin, demand, supplier quality, and trends
            """
        )

        st.markdown("### Quick Margin Reference")
        examples = [
            ("Pet bandana", 14.99, 2.50),
            ("Posture corrector", 24.99, 5.00),
            ("Phone holder", 12.99, 3.50),
            ("LED strip 5m", 19.99, 4.00),
            ("Resistance bands set", 15.99, 3.00),
        ]
        for name, sell, source in examples:
            st.code(f"{name}: {quick_margin_check(sell, source)}")
    else:
        # --- Run search ---
        with st.spinner("Searching eBay..."):
            ebay_results = search_ebay(
                query=query,
                min_price=min_price,
                max_price=max_price,
                sort="best_match",
                limit=result_limit,
            )

        with st.spinner("Searching AliExpress..."):
            ali_results = search_aliexpress(
                query=query,
                max_price=ali_max_price,
                sort="orders",
                limit=result_limit,
                min_orders=min_ali_orders,
                min_rating=min_ali_rating,
            )

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("eBay listings found", len(ebay_results))
        col2.metric("AliExpress products found", len(ali_results))

        if not ebay_results:
            st.error("No eBay results found. Try broadening your search or price range.")
            st.stop()

        if not ali_results:
            st.warning(
                "No AliExpress results found. This may be due to scraping restrictions. "
                "Try a different keyword or check your network connection."
            )
            st.stop()

        # --- Analyze ---
        with st.spinner("Matching products and calculating margins..."):
            df = analyze_opportunities(
                ebay_products=ebay_results,
                ali_products=ali_results,
                keyword=query,
                min_similarity=min_similarity,
                use_promoted=use_promoted,
                include_trends=include_trends,
            )

        col3.metric("Profitable matches", len(df))

        if df.empty:
            st.warning(
                "No profitable matches found. Try:\n"
                "- Lowering the match confidence threshold\n"
                "- Broadening the price range\n"
                "- Using a different keyword"
            )
            st.stop()

        # --- Top Opportunities ---
        st.subheader(f"🏆 Top Opportunities for \"{query}\"")

        # Summary cards for top 3
        top3 = df.head(3)
        cols = st.columns(3)
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols[i]:
                score = row["composite_score"]
                score_class = "score-high" if score >= 70 else "score-mid" if score >= 50 else "score-low"
                profit_class = "profit-positive" if row["net_profit"] > 0 else "profit-negative"

                st.markdown(f"<span class='{score_class}'>Score: {score}/100</span>", unsafe_allow_html=True)
                st.markdown(f"**{row['ebay_title'][:50]}...**")
                st.markdown(
                    f"eBay: **${row['ebay_price']:.2f}** → Ali: **${row['ali_cost']:.2f}**"
                )
                st.markdown(
                    f"<span class='{profit_class}'>Profit: ${row['net_profit']:.2f} "
                    f"({row['margin_pct']}%)</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"ROI: {row['roi_pct']}% | Match: {row['match_confidence']:.0%}")

        # --- Full table ---
        st.subheader("📋 All Opportunities")

        display_df = df[[
            "composite_score", "ebay_title", "ebay_price", "ali_cost",
            "net_profit", "margin_pct", "roi_pct", "ali_orders",
            "ali_rating", "match_confidence",
        ]].rename(columns={
            "composite_score": "Score",
            "ebay_title": "Product",
            "ebay_price": "eBay Price",
            "ali_cost": "Ali Cost",
            "net_profit": "Profit",
            "margin_pct": "Margin %",
            "roi_pct": "ROI %",
            "ali_orders": "Ali Orders",
            "ali_rating": "Ali Rating",
            "match_confidence": "Match",
        })

        st.dataframe(
            display_df.style
            .format({
                "Score": "{:.0f}",
                "eBay Price": "${:.2f}",
                "Ali Cost": "${:.2f}",
                "Profit": "${:.2f}",
                "Margin %": "{:.1f}%",
                "ROI %": "{:.0f}%",
                "Ali Rating": "{:.1f}",
                "Match": "{:.0%}",
            })
            .background_gradient(subset=["Score"], cmap="RdYlGn", vmin=0, vmax=100)
            .background_gradient(subset=["Margin %"], cmap="RdYlGn", vmin=0, vmax=60),
            use_container_width=True,
            height=400,
        )

        # --- Charts ---
        st.subheader("📊 Visualizations")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            fig_margin = px.bar(
                df.head(10),
                x="ebay_title",
                y="net_profit",
                color="margin_pct",
                color_continuous_scale="RdYlGn",
                title="Top 10 by Profit ($)",
                labels={"ebay_title": "Product", "net_profit": "Net Profit ($)"},
            )
            fig_margin.update_xaxes(tickangle=45, tickfont_size=9)
            fig_margin.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig_margin, use_container_width=True)

        with chart_col2:
            fig_scatter = px.scatter(
                df,
                x="ali_cost",
                y="net_profit",
                size="composite_score",
                color="margin_pct",
                color_continuous_scale="RdYlGn",
                hover_name="ebay_title",
                title="Source Cost vs Profit (bubble = score)",
                labels={
                    "ali_cost": "AliExpress Cost ($)",
                    "net_profit": "Net Profit ($)",
                    "margin_pct": "Margin %",
                },
            )
            fig_scatter.update_layout(height=400)
            st.plotly_chart(fig_scatter, use_container_width=True)

        # --- Fee breakdown for selected product ---
        st.subheader("🔍 Fee Breakdown")
        selected_idx = st.selectbox(
            "Select a product for detailed breakdown",
            options=df.index,
            format_func=lambda i: f"#{i+1}: {df.loc[i, 'ebay_title'][:60]}",
        )

        if selected_idx is not None:
            row = df.loc[selected_idx]
            bc1, bc2 = st.columns(2)

            with bc1:
                st.markdown("**Revenue**")
                st.write(f"eBay sell price: **${row['ebay_price']:.2f}**")
                st.markdown("**Costs**")
                st.write(f"AliExpress source: ${row['ali_cost']:.2f}")
                st.write(f"eBay fee (13.25% + $0.30): ${row['ebay_fee']:.2f}")
                st.write(f"Payment fee (2.9% + $0.30): ${row['payment_fee']:.2f}")
                if use_promoted:
                    st.write(f"Promoted listing (3%): ${row['promoted_fee']:.2f}")

            with bc2:
                fig_pie = go.Figure(
                    data=[go.Pie(
                        labels=["Your Profit", "Source Cost", "eBay Fee", "Payment Fee"]
                        + (["Promoted Fee"] if use_promoted and row["promoted_fee"] > 0 else []),
                        values=[
                            max(row["net_profit"], 0),
                            row["ali_cost"],
                            row["ebay_fee"],
                            row["payment_fee"],
                        ] + ([row["promoted_fee"]] if use_promoted and row["promoted_fee"] > 0 else []),
                        marker_colors=["#00c853", "#ff6d00", "#ff1744", "#d500f9", "#ffab00"],
                        hole=0.4,
                    )]
                )
                fig_pie.update_layout(
                    title="Cost Breakdown",
                    height=300,
                    margin=dict(t=40, b=0, l=0, r=0),
                )
                st.plotly_chart(fig_pie, use_container_width=True)

        # --- Export ---
        st.subheader("💾 Export")
        csv = df.to_csv(index=False)
        st.download_button(
            "Download CSV",
            csv,
            f"reseller_analysis_{query.replace(' ', '_')}.csv",
            "text/csv",
        )

        # Links column
        with st.expander("🔗 Product Links"):
            for _, row in df.iterrows():
                st.markdown(
                    f"**{row['ebay_title'][:50]}** — "
                    f"[eBay]({row['ebay_url']}) | [AliExpress]({row['ali_url']})"
                )

# ---------------------------------------------------------------------------
# Tab 2: Margin Calculator
# ---------------------------------------------------------------------------
with tab_margin_calc:
    st.subheader("🧮 Quick Margin Calculator")
    st.caption("Plug in any sell price / source cost to see real margins after fees")

    mc1, mc2 = st.columns(2)
    with mc1:
        calc_sell = st.number_input("eBay sell price ($)", value=24.99, min_value=0.01, step=0.50, key="calc_sell")
    with mc2:
        calc_source = st.number_input("AliExpress source cost ($)", value=5.50, min_value=0.01, step=0.50, key="calc_source")

    calc_promoted = st.checkbox("Include promoted listing fee", key="calc_promo")

    m = calculate_margin(calc_sell, calc_source, use_promoted=calc_promoted)

    mc_cols = st.columns(4)
    mc_cols[0].metric("Net Profit", f"${m['net_profit']:.2f}")
    mc_cols[1].metric("Margin", f"{m['margin_pct']}%")
    mc_cols[2].metric("ROI", f"{m['roi_pct']}%")

    verdict = "✅ GO" if m["margin_pct"] >= 20 else "⚠️ THIN" if m["margin_pct"] >= 10 else "❌ SKIP"
    mc_cols[3].metric("Verdict", verdict)

    st.markdown("**Fee breakdown:**")
    st.write(f"eBay fee: \${m['ebay_fee']:.2f} | Payment fee: \${m['payment_fee']:.2f}" +
             (f" | Promoted: \${m['promoted_fee']:.2f}" if calc_promoted else ""))

    # Batch calculator
    st.divider()
    st.subheader("📦 Batch Margin Check")
    st.caption("Paste sell_price,source_cost per line")

    batch_input = st.text_area(
        "Batch input (sell_price,source_cost per line)",
        placeholder="24.99,5.50\n14.99,3.00\n19.99,8.00",
        height=120,
    )

    if batch_input.strip():
        batch_rows = []
        for line in batch_input.strip().split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    sp, sc = float(parts[0]), float(parts[1])
                    bm = calculate_margin(sp, sc)
                    verdict = "GO" if bm["margin_pct"] >= 20 else "THIN" if bm["margin_pct"] >= 10 else "SKIP"
                    batch_rows.append({
                        "Sell": sp, "Source": sc, "Profit": bm["net_profit"],
                        "Margin %": bm["margin_pct"], "ROI %": bm["roi_pct"], "Verdict": verdict,
                    })
                except ValueError:
                    continue

        if batch_rows:
            st.dataframe(pd.DataFrame(batch_rows), use_container_width=True)

# ---------------------------------------------------------------------------
# Tab 3: Trends Scout
# ---------------------------------------------------------------------------
with tab_trends:
    st.subheader("📈 Google Trends Scout")
    st.caption("Check demand trajectory before committing to a product")

    trend_query = st.text_input("Keyword to check", placeholder="e.g. posture corrector", key="trend_q")

    if trend_query:
        with st.spinner("Fetching Google Trends data..."):
            score = get_trend_score(trend_query)
            velocity = get_trend_velocity(trend_query)

        tc1, tc2 = st.columns(2)

        if score is not None:
            tc1.metric("Avg Interest (0-100)", f"{score:.0f}")
        else:
            tc1.warning("Could not fetch trend score")

        if velocity is not None:
            direction = "📈 Growing" if velocity > 5 else "📉 Declining" if velocity < -5 else "➡️ Stable"
            tc2.metric("Trend Velocity", f"{velocity:+.1f}%", delta=direction)
        else:
            tc2.warning("Could not calculate velocity")

        # Inline pytrends chart
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="en-US", tz=360)
            pytrends.build_payload([trend_query], timeframe="today 3-m", geo="US")
            trend_df = pytrends.interest_over_time()

            if not trend_df.empty:
                fig_trend = px.line(
                    trend_df,
                    y=trend_query,
                    title=f"Google Trends: \"{trend_query}\" (last 3 months)",
                    labels={"date": "", trend_query: "Interest"},
                )
                fig_trend.update_layout(height=300, showlegend=False)
                st.plotly_chart(fig_trend, use_container_width=True)
        except Exception:
            st.info("Install pytrends for trend charts: pip install pytrends")

        # Compare multiple keywords
        st.divider()
        st.subheader("Compare keywords")
        compare_input = st.text_input(
            "Comma-separated keywords (max 5)",
            placeholder="pet bandana, dog collar, cat toy",
            key="trend_compare",
        )

        if compare_input:
            keywords = [k.strip() for k in compare_input.split(",") if k.strip()][:5]
            with st.spinner("Comparing trends..."):
                try:
                    pytrends = TrendReq(hl="en-US", tz=360)
                    pytrends.build_payload(keywords, timeframe="today 3-m", geo="US")
                    cmp_df = pytrends.interest_over_time()

                    if not cmp_df.empty:
                        fig_cmp = px.line(
                            cmp_df[keywords],
                            title="Trend Comparison (3 months)",
                        )
                        fig_cmp.update_layout(height=350)
                        st.plotly_chart(fig_cmp, use_container_width=True)
                except Exception as e:
                    st.error(f"Trends comparison failed: {e}")

# ---------------------------------------------------------------------------
# Tab 4: Sold Validation
# ---------------------------------------------------------------------------
with tab_sold:
    st.subheader("✅ eBay Sold Listings Validation")
    st.caption(
        "Check what actually SOLD on eBay — not just what's listed. "
        "This validates real demand before you commit."
    )

    sold_query = st.text_input("Product to validate", placeholder="e.g. pet bandana", key="sold_q")

    if sold_query:
        with st.spinner("Searching eBay sold listings..."):
            sold_results = search_ebay_sold(sold_query, limit=20)

        if sold_results:
            st.success(f"Found {len(sold_results)} recent sales")

            prices = [p.price for p in sold_results if p.price > 0]
            if prices:
                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("Avg Sold Price", f"${sum(prices)/len(prices):.2f}")
                sc2.metric("Min Sold", f"${min(prices):.2f}")
                sc3.metric("Max Sold", f"${max(prices):.2f}")
                sc4.metric("Sales Found", len(prices))

                fig_hist = px.histogram(
                    x=prices,
                    nbins=15,
                    title=f"Sold Price Distribution: \"{sold_query}\"",
                    labels={"x": "Sold Price ($)", "y": "Count"},
                )
                fig_hist.update_layout(height=300)
                st.plotly_chart(fig_hist, use_container_width=True)

            # List sold items
            for p in sold_results:
                st.markdown(
                    f"**${p.price:.2f}** — {p.title[:70]} "
                    + (f"[link]({p.url})" if p.url else "")
                )
        else:
            st.warning("No sold listings found. Try a different keyword.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Reseller Tool v0.1.0 | eBay fees: 13.25% + \$0.30 | "
    "Payment: 2.9% + \$0.30 | Data from SerpApi + AliExpress"
)
