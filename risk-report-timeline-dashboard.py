import streamlit as st
import plotly.graph_objects as go
from collections import defaultdict
from datetime import datetime
import re
import pickle

st.set_page_config(layout="wide")

# -----------------------------
# CONFIG
# -----------------------------
risk_map = {"L": 1, "M": 2, "H": 3}
risk_label = {1: "Low", 2: "Moderate", 3: "High"}
risk_color = {1: "green", 2: "orange", 3: "red"}

# -----------------------------
# DATE PARSER
# -----------------------------
def get_date(doc):
    name = doc.get("name", "")

    def parse_date(date_str):
        normalized = re.sub(r"[./]", "-", date_str)
        formats = ["%d-%m-%Y", "%m-%d-%Y", "%d-%m-%y", "%m-%d-%y"]

        for fmt in formats:
            try:
                dt = datetime.strptime(normalized, fmt)
                if dt.year < 100:
                    dt = dt.replace(year=2000 + dt.year)
                return dt
            except:
                continue
        return None

    match = re.search(r"Doc Date(.{0,40})", name, re.IGNORECASE)
    if match:
        chunk = match.group(1)
        m = re.search(r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})", chunk)
        if m:
            dt = parse_date(m.group(1))
            if dt:
                return dt

    all_dates = re.findall(r"\d{1,2}[-./]\d{1,2}[-./]\d{2,4}", name)
    for d in all_dates:
        dt = parse_date(d)
        if dt:
            return dt

    return datetime.fromisoformat(doc["created_at"]).replace(tzinfo=None)

# -----------------------------
# MAIN FUNCTION
# -----------------------------
def get_plot(final_results):
    # -----------------------------
    # INPUT DATA
    # -----------------------------
    data = final_results

    # -----------------------------
    # CONFIG
    # -----------------------------
    risk_map = {"L": 1, "M": 2, "H": 3}
    risk_label = {1: "Low", 2: "Moderate", 3: "High"}
    risk_color = {1: "green", 2: "orange", 3: "red"}

    MIN_OFFSET = 1
    PADDING = 2

    # -----------------------------
    # STEP 1: ASSIGN DATES
    # -----------------------------
    date_buckets = {
        "L": (datetime(2026, 1, 1), datetime(2026, 1, 31)),
        "M": (datetime(2026, 2, 1), datetime(2026, 2, 28)),
        "H": (datetime(2026, 3, 1), datetime(2026, 3, 31)),
    }

    def random_date(start, end):
        delta = end - start
        return start + timedelta(days=random.randint(0, delta.days))

    def get_date(doc):
        """
        Robust date extractor:
        1. Try extracting date near 'Doc Date'
        2. Else extract ANY date from name
        3. Else fallback to created_at

        Supports formats:
        - 1.30.2024, 6.11.23
        - 12-12-2014, 1-30-2024
        - 12/05/23
        """

        name = doc.get("name", "")

        # -----------------------------
        # HELPER: parse date string
        # -----------------------------
        def parse_date(date_str):
            normalized = re.sub(r"[./]", "-", date_str)

            formats = [
                "%d-%m-%Y",
                "%m-%d-%Y",
                "%d-%m-%y",
                "%m-%d-%y",
                "%Y-%m-%d"
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(normalized, fmt)

                    # Fix 2-digit year
                    if dt.year < 100:
                        dt = dt.replace(year=2000 + dt.year)

                    return dt
                except ValueError:
                    continue

            return None

        # -----------------------------
        # STEP 1: Try "Doc Date"
        # -----------------------------
        match = re.search(r"Doc Date(.{0,40})", name, re.IGNORECASE)

        if match:
            chunk = match.group(1)

            date_match = re.search(r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})", chunk)

            if date_match:
                dt = parse_date(date_match.group(1))
                if dt:
                    return dt

        # -----------------------------
        # STEP 2: Try ANY date in name
        # -----------------------------
        all_dates = re.findall(r"\d{1,2}[-./]\d{1,2}[-./]\d{2,4}", name)

        for d in all_dates:
            dt = parse_date(d)
            if dt:
                return dt

        # -----------------------------
        # STEP 3: Fallback → created_at
        # -----------------------------
        created_at = doc.get("created_at")

        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)

                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)

                return dt
            except Exception:
                pass

        # अंतिम fallback
        return datetime.now()
        
    for doc in data:
        # risk = doc["risk_info"]["document_risk_score"]
        # start, end = date_buckets.get(risk, (datetime(2026,1,1), datetime(2026,3,31)))
        doc["display_date"] = get_date(doc)

    docs = sorted(data, key=lambda x: x["display_date"])
    # docs[-1]["display_date"] = docs[-2]["display_date"]
    # -----------------------------
    # STEP 2: FIRST PASS (same)
    # -----------------------------
    seen_keywords = set()
    current_max_risk = 0

    cumulative_by_risk = {1: 0, 2: 0, 3: 0}
    max_by_risk = {1: 0, 2: 0, 3: 0}

    for doc in docs:
        doc_risk = risk_map.get(doc["risk_info"]["document_risk_score"], 0)
        ann = doc.get("annotations", {}).get("claim-characteristics", {}).get("annotations", [])

        current_keywords = {(a.get("Characteristic"), a.get("Question")) for a in ann}
        new_keywords = current_keywords - seen_keywords

        if doc_risk > current_max_risk:
            current_max_risk = doc_risk

        relevant = set()
        for cat, kw in new_keywords:
            for a in ann:
                if a.get("Question") == kw and a.get("Characteristic") == cat:
                    if risk_map.get(a.get("RiskCategory"), 0) == current_max_risk:
                        relevant.add((cat, kw))

        cumulative_by_risk[current_max_risk] += len(relevant)
        max_by_risk[current_max_risk] = max(
            max_by_risk[current_max_risk],
            cumulative_by_risk[current_max_risk]
        )

        seen_keywords.update(current_keywords)

    # -----------------------------
    # STEP 3: REGION HEIGHTS
    # -----------------------------
    low_height = max_by_risk[1] + PADDING + MIN_OFFSET
    mod_height = max_by_risk[2] + PADDING + MIN_OFFSET
    high_height = max_by_risk[3] + PADDING + MIN_OFFSET

    risk_base = {
        1: 0,
        2: low_height,
        3: low_height + mod_height
    }

    total_height = low_height + mod_height + high_height

    # -----------------------------
    # STEP 4: SECOND PASS + GROUPING
    # -----------------------------
    seen_keywords = set()
    current_max_risk = 0
    cumulative_by_risk = {1: 0, 2: 0, 3: 0}
    cumulative_keywords_by_risk = {1: set(), 2: set(), 3: set()}

    grouped = defaultdict(list)

    prev_date = None
    for doc in docs:
        doc_risk = risk_map.get(doc["risk_info"]["document_risk_score"], 0)
        ann = doc.get("annotations", {}).get("claim-characteristics", {}).get("annotations", [])

        current_keywords = {(a.get("Characteristic"), a.get("Question")) for a in ann}
        new_keywords = current_keywords - seen_keywords

        if doc_risk > current_max_risk:
            current_max_risk = doc_risk

        relevant = set()
        for cat, kw in new_keywords:
            for a in ann:
                if a.get("Question") == kw and a.get("Characteristic") == cat:
                    if risk_map.get(a.get("RiskCategory"), 0) == current_max_risk:
                        relevant.add((cat, kw))

        cumulative_by_risk[current_max_risk] += len(relevant)
        
        seen_keywords.update(current_keywords)

        y_val = risk_base[current_max_risk] + cumulative_by_risk[current_max_risk] + MIN_OFFSET
        color = risk_color[current_max_risk]

        # -----------------------------
        # BUILD PER-DOC HOVER
        # -----------------------------
        doc_id = doc.get("id")

        doc_url = f"https://claimlens.empro.doclens.ai/claim-file/15/?dep=3&folder=5&defaultDoc={doc_id}"

        hover = (
            f"<a href='{doc_url}' target='_blank' "
            f"style='text-decoration:underline;'>"
            f"<b>Document {doc_id}</b></a><br>"
        )
        hover += f"Claim Risk: <span style='color:{color}'><b>{risk_label[current_max_risk]}</b></span>"
        # hover += f"Cumulative Signals Count: <b>{cumulative_by_risk[current_max_risk]}</b><br>"

        # NEW: cumulative keyword list
        # if cumulative_keywords_by_risk[current_max_risk]:
        #     hover += "<b>All Signals So Far:</b><br>"

        #     temp_all = {}
        #     for cat, kw in cumulative_keywords_by_risk[current_max_risk]:
        #         temp_all.setdefault(cat, []).append(kw)

        #     for cat, kws in temp_all.items():
        #         hover += f"<b>{cat}</b>: <span style='color:{color}'>{', '.join(set(kws))}</span><br>"

        hover += "<br>"

        # existing new signals
        if relevant:
            hover += f"<b>New {risk_label[current_max_risk]} Risk Signals: ({len(relevant)})</b><br>"
            temp = {}
            for cat, kw in relevant:
                temp.setdefault(cat, []).append(kw)

            for cat, kws in temp.items():
                hover += f"<b>{cat}</b>: <span style='color:{color}'>{', '.join(set(kws))}</span><br>"
        else:
            hover += f"<b>No new {risk_label[current_max_risk]} signals</b><br>"

        hover += "<br>"

        grouped[doc["display_date"]].append({
            "hover": hover,
            "y": y_val,
            "color": color,
            "risk_level": current_max_risk,
            "cumulative_snapshot": {
                1: cumulative_keywords_by_risk[1].copy(),
                2: cumulative_keywords_by_risk[2].copy(),
                3: cumulative_keywords_by_risk[3].copy()
            }
        })
        cumulative_keywords_by_risk[current_max_risk].update(relevant)

    # -----------------------------
    # STEP 5: BUILD FINAL PLOT DATA
    # -----------------------------
    x_vals = []
    y_vals = []
    colors = []
    hover_texts = []

    sorted_dates = sorted(grouped.keys())
    doc_ids_per_point = []

    for i, date in enumerate(sorted_dates):
        ids = [doc.get("id") for doc in data if doc["display_date"] == date]
        doc_ids_per_point.append(ids)

        entries = grouped[date]

        # Take LAST entry of that date (latest state)
        last_entry = entries[-1]

        risk_level = last_entry["risk_level"]
        color = last_entry["color"]
        y_val = last_entry["y"]

        cumulative_snapshot = last_entry["cumulative_snapshot"]

        # -----------------------------
        # BUILD FINAL HOVER
        # -----------------------------
        combined_hover = f"<b>Date: {date.strftime('%Y-%m-%d')}</b><br><br>"

        # ✅ CUMULATIVE (correct snapshot now)
        if cumulative_snapshot[risk_level]:
            combined_hover += f"<b>Cumulative {risk_label[risk_level]} Signals So Far: ({len(cumulative_snapshot[risk_level])})</b><br>"

            temp_all = {}
            for cat, kw in cumulative_snapshot[risk_level]:
                temp_all.setdefault(cat, []).append(kw)

            for cat, kws in temp_all.items():
                combined_hover += f"<b>{cat}</b>: <span style='color:{color}'>{', '.join(set(kws))}</span><br>"

            combined_hover += "<br>"

        # ✅ PER-DOC DETAILS (THIS WAS MISSING EFFECTIVELY)
        for e in entries:
            combined_hover += e["hover"]

        x_vals.append(i)
        y_vals.append(y_val)
        colors.append(color)
        hover_texts.append(combined_hover)
    # -----------------------------
    # STEP 6: PLOT
    # -----------------------------
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode='markers+lines',
        marker=dict(
            size=14,
            color=colors,
            line=dict(width=2, color='black')
        ),
        line=dict(width=2),
        text=hover_texts,
        hovertemplate="%{text}<extra></extra>",
        customdata=[doc_ids_per_point]  # we’ll define this
    ))

    def open_doc(trace, points, state):
        if points.point_inds:
            idx = points.point_inds[0]
            doc_ids = trace.customdata[idx]

            # open first doc (or modify logic)
            doc_id = doc_ids[-1]

            url = f"https://claimlens.empro.doclens.ai/claim-file/15/?dep=3&folder=5&defaultDoc={doc_id}"
            import webbrowser
            webbrowser.open_new_tab(url)

    fig.data[0].on_click(open_doc)

    # -----------------------------
    # BACKGROUND REGIONS
    # -----------------------------
    fig.add_shape(type="rect", xref="paper", yref="y",
                x0=0, x1=1, y0=0, y1=low_height,
                fillcolor="green", opacity=0.08, layer="below", line_width=0)

    fig.add_shape(type="rect", xref="paper", yref="y",
                x0=0, x1=1, y0=low_height, y1=low_height+mod_height,
                fillcolor="orange", opacity=0.08, layer="below", line_width=0)

    fig.add_shape(type="rect", xref="paper", yref="y",
                x0=0, x1=1, y0=low_height+mod_height, y1=total_height,
                fillcolor="red", opacity=0.08, layer="below", line_width=0)

    # -----------------------------
    # FINAL LAYOUT
    # -----------------------------
    fig.update_layout(
        title="Claim Risk Progression Timeline",

        xaxis=dict(
            title="Date Document Received (Grouped by Date)",
            tickvals=x_vals,
            ticktext=[d.strftime("%b %d, %Y") for d in sorted_dates],
            tickfont=dict(size=14)
        ),

        yaxis=dict(
            title="Claim Risk",
            tickvals=[
                low_height / 2,
                low_height + mod_height / 2,
                low_height + mod_height + high_height / 2
            ],
            ticktext=["Low Risk", "Moderate Risk", "High Risk"],
            tickfont=dict(size=14)
        ),

        template="plotly_white",
        height=700,
        width=1200,
        hovermode="closest",
        margin=dict(t=80, b=80),
        hoverlabel=dict(
            bgcolor="white",
            font_size=13,
            font_family="Arial",
            font_color="black",
            bordercolor="lightgrey",
            align="left"
        )
    )

    # fig.show()
    return fig, grouped, sorted_dates


# -----------------------------
# UI
# -----------------------------
st.markdown("<img src='https://awsmp-logos.s3.amazonaws.com/seller-s26bqc5zvqci2/28b3758023bda4842d49ef0317e57566.png' width='100'>", unsafe_allow_html=True)
st.title("📊 Claim Risk Timeline")

import pickle

claim_file = st.selectbox(
    "Select a claim file",
    ["138226", "170949"]
)

claim_file_mapping = {
    "138226": 16,
    "170949": 15
}

with open(f"risk-report-timeline-results-{claim_file}.pkl", "rb") as f:
    loaded_list = pickle.load(f)

print(loaded_list)

data = loaded_list

if not data:
    st.warning("No data loaded")
    st.stop()

fig, grouped, date_keys = get_plot(data)



st.plotly_chart(fig, use_container_width=True)

# selected_index = st.selectbox(
#     "Select Date: ",
#     range(len(date_keys)),
#     format_func=lambda i: date_keys[i].strftime("%b %d, %Y")
# )
# -----------------------------
# SHOW DETAILS
# -----------------------------
# selected_date = date_keys[selected_index]
# entries = grouped[selected_date]

# st.subheader(f"Documents on {selected_date.strftime('%b %d, %Y')}")

# docs = [doc for doc in data if doc["display_date"] == selected_date]

# for doc in docs:
#     doc_id = doc["id"]

#     url = f"https://claimlens.empro.doclens.ai/claim-file/{claim_file_mapping[claim_file]}/?dept=3&folder=5&defaultDoc={doc_id}"

#     st.markdown(f"### 🔗 [Document {doc_id}]({url})")

    # st.write(f"Risk: **{risk_label[doc['risk']]}**")
    # st.write(f"Cumulative Signals: {e['cumulative']}")

    # if e["new_signals"]:
    #     st.write("New Signals:")
    #     for cat, kw in e["new_signals"]:
    #         st.write(f"- {cat}: {kw}")
    # else:
    #     st.write("No new signals")

st.divider()