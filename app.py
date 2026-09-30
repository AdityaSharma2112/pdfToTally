import streamlit as st
import pandas as pd
import tempfile
import os
import json
from bank_parser import (
    detect_and_parse_pdf, 
    SBIBankParser, 
    HDFCBankParser, 
    GenericBankParser, 
    CustomColumnBankParser, 
    extract_pdf_raw_table_sample
)
from tally_xml_generator import TallyXMLGenerator
from rules_engine import NarrationRulesEngine
from llm_mapper import LLMColumnMapper

st.set_page_config(
    page_title="Bank Statement to Tally XML Converter",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    .stButton>button {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        font-weight: 600;
        border: none;
        padding: 0.5rem 1.0rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🏦 Bank Statement PDF to Tally XML Converter</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Convert Bank Statements into Importable Tally Vouchers with Manual Header Mapping & OpenAI-Compatible AI Column Mapping</div>', unsafe_allow_html=True)

# Initialize Session State
RULES_FILE = "narration_rules.json"
if "rules_engine" not in st.session_state:
    st.session_state.rules_engine = NarrationRulesEngine(RULES_FILE if os.path.exists(RULES_FILE) else None)

if "column_mapping" not in st.session_state:
    st.session_state.column_mapping = {
        "date": 0,
        "value_date": None,
        "narration": 2,
        "cheque_no": 3,
        "debit": 4,
        "credit": 5,
        "balance": 6
    }

if "use_custom_mapping" not in st.session_state:
    st.session_state.use_custom_mapping = False

# Sidebar Configuration
st.sidebar.header("⚙️ Tally Import Configuration")

company_name = st.sidebar.text_input("Tally Company Name", value="GUPTA BUILDING MATERIAL AND MARBEL")
bank_ledger = st.sidebar.text_input("Tally Bank Ledger Name", value="State Bank of India")
default_party_ledger = st.sidebar.text_input("Default / Fallback Ledger", value="SUSPENS")
start_voucher_num = st.sidebar.number_input("Starting Voucher Number", min_value=1, value=1, step=1)

bank_option = st.sidebar.selectbox(
    "Select Bank Profile",
    ["Auto Detect", "Custom / Manual Header Mapping", "State Bank of India (SBI)", "HDFC Bank", "Generic Auto-Detect"]
)

# LLM Configuration Section in Sidebar
with st.sidebar.expander("🤖 OpenAI-Compatible LLM Settings"):
    llm_api_key = st.text_input("API Key", type="password", placeholder="sk-...", help="API Key for OpenAI, Groq, OpenRouter, etc.")
    llm_base_url = st.text_input("Base URL", value="https://api.openai.com/v1", help="Supports Ollama (http://localhost:11434/v1), Groq, OpenRouter, vLLM, etc.")
    llm_model_name = st.text_input("Model Name", value="gpt-4o-mini", help="e.g. gpt-4o-mini, llama3, deepseek-chat, mistral")

# Main Navigation Tabs
tab_convert, tab_mapping, tab_rules = st.tabs([
    "📄 Convert PDF to Tally XML", 
    "🗂️ Header & Column Mapper", 
    "🎯 Narration -> Ledger Rules"
])

# TAB 1: CONVERT PDF
with tab_convert:
    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader("Upload Bank Statement PDF file", type=["pdf"], key="pdf_uploader")

    with col2:
        st.info("💡 **Header Mapping:** Map column headers visually in the 'Header & Column Mapper' tab or use Auto-Detect.")

    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        with st.spinner("Parsing PDF statement & applying ledger mapping rules..."):
            try:
                st.session_state.rules_engine.default_ledger = default_party_ledger

                if bank_option == "Custom / Manual Header Mapping" or st.session_state.use_custom_mapping:
                    parser = CustomColumnBankParser(st.session_state.column_mapping)
                    metadata, transactions = parser.parse(tmp_path, rules_engine=st.session_state.rules_engine)
                elif bank_option == "State Bank of India (SBI)":
                    parser = SBIBankParser()
                    metadata, transactions = parser.parse(tmp_path, rules_engine=st.session_state.rules_engine)
                elif bank_option == "HDFC Bank":
                    parser = HDFCBankParser()
                    metadata, transactions = parser.parse(tmp_path, rules_engine=st.session_state.rules_engine)
                elif bank_option == "Generic Auto-Detect":
                    parser = GenericBankParser()
                    metadata, transactions = parser.parse(tmp_path, rules_engine=st.session_state.rules_engine)
                else:
                    metadata, transactions = detect_and_parse_pdf(tmp_path, rules_engine=st.session_state.rules_engine)

                os.unlink(tmp_path)

            except Exception as e:
                st.error(f"Error reading PDF: {str(e)}")
                transactions = []

        if transactions:
            st.success(f"Successfully extracted & mapped {len(transactions)} transactions!")

            df = pd.DataFrame(transactions)
            total_receipts = df['credit'].sum()
            total_payments = df['debit'].sum()
            net_flow = total_receipts - total_payments

            # Summary Cards
            mcol1, mcol2, mcol3, mcol4 = st.columns(4)
            mcol1.metric("Total Transactions", len(df))
            mcol2.metric("Total Receipts (CR)", f"₹{total_receipts:,.2f}")
            mcol3.metric("Total Payments (DR)", f"₹{total_payments:,.2f}")
            mcol4.metric("Net Flow", f"₹{net_flow:,.2f}")

            st.markdown("### 📋 Interactive Transaction & Ledger Review")
            st.caption("Edit the **Mapped Ledger** column directly below before exporting to Tally:")

            df['Voucher Type'] = df.apply(lambda r: "Receipt" if r['credit'] > 0 else "Payment", axis=1)
            df['Amount (₹)'] = df.apply(lambda r: r['credit'] if r['credit'] > 0 else r['debit'], axis=1)
            
            if 'counter_ledger' not in df.columns:
                df['counter_ledger'] = default_party_ledger

            edit_df = df[['date', 'Voucher Type', 'Amount (₹)', 'counter_ledger', 'narration', 'cheque_no', 'balance']].copy()
            edit_df.rename(columns={'counter_ledger': 'Mapped Ledger'}, inplace=True)

            edited_df = st.data_editor(
                edit_df,
                num_rows="fixed",
                width="stretch",
                column_config={
                    "Mapped Ledger": st.column_config.TextColumn(
                        "Mapped Ledger",
                        help="Target Tally Ledger for this transaction. Edit directly if needed.",
                        required=True
                    )
                }
            )

            # Build final transaction list
            final_transactions = []
            for idx, row in edited_df.iterrows():
                orig_tx = transactions[idx].copy()
                orig_tx['counter_ledger'] = row['Mapped Ledger']
                final_transactions.append(orig_tx)

            # Generate XML
            generator = TallyXMLGenerator(
                company_name=company_name,
                bank_ledger=bank_ledger,
                default_counter_ledger=default_party_ledger
            )
            xml_string = generator.generate_xml(final_transactions, start_voucher_num=start_voucher_num)

            st.markdown("### 📥 Download Tally Import File")
            st.download_button(
                label="⬇️ Download Tally XML File",
                data=xml_string,
                file_name="tally_bank_vouchers.xml",
                mime="text/xml",
                help="Import directly into Tally Prime via Import Data -> Vouchers"
            )

            with st.expander("🔍 View Generated XML Code"):
                st.code(xml_string[:2500] + "\n...", language="xml")

        else:
            st.warning("No transactions could be extracted. Check the PDF format or try Custom Header Mapper tab.")
    else:
        st.info("👆 Upload a Bank Statement PDF above to start automatic processing.")

# TAB 2: HEADER & COLUMN MAPPER
with tab_mapping:
    st.markdown("### 🗂️ Map Statement Columns to Tally Fields")
    st.markdown("Select column headers by their **actual names in the statement table** or use **AI Auto-Detection**.")

    uploaded_pdf_map = st.file_uploader("Upload PDF to inspect table headers", type=["pdf"], key="pdf_mapper_uploader")

    extracted_headers, sample_rows = [], []
    if uploaded_pdf_map is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_pdf_map.getvalue())
            tmp_path_map = tmp_file.name

        extracted_headers, sample_rows = extract_pdf_raw_table_sample(tmp_path_map)
        os.unlink(tmp_path_map)

        if extracted_headers or sample_rows:
            st.success(f"Detected {len(extracted_headers)} table headers from PDF:")
            st.dataframe(pd.DataFrame(sample_rows, columns=extracted_headers if len(extracted_headers) == len(sample_rows[0]) else None), width="stretch")
        else:
            st.warning("Could not extract structured table headers from this PDF page. Default headers will be displayed.")

    # Build dropdown choices using actual statement column names!
    if extracted_headers:
        header_options = ["(None / Skip)"] + [f"{i+1}. {h}" for i, h in enumerate(extracted_headers)]
    else:
        header_options = ["(None / Skip)"] + [f"{i+1}. Column {i+1}" for i in range(10)]

    # Helper function to get index in header_options
    def get_option_idx(col_idx):
        if col_idx is None:
            return 0
        if 0 <= col_idx < len(header_options) - 1:
            return col_idx + 1
        return 0

    # AI Auto-Mapping Button
    col_ai1, col_ai2 = st.columns([1, 2])
    with col_ai1:
        if st.button("🤖 Auto-Detect Header Mapping via AI"):
            if not extracted_headers and not sample_rows:
                st.error("Please upload a PDF file above first to extract sample table headers for AI analysis.")
            else:
                with st.spinner(f"Querying AI endpoint ({llm_model_name} @ {llm_base_url})..."):
                    try:
                        mapper = LLMColumnMapper(api_key=llm_api_key, base_url=llm_base_url, model_name=llm_model_name)
                        ai_mapping = mapper.auto_map_columns(extracted_headers, sample_rows)
                        st.session_state.column_mapping.update(ai_mapping)
                        st.session_state.use_custom_mapping = True
                        st.success(f"AI Auto-Detection Complete! Header mapping updated.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"AI Mapping Error: {str(ex)}")

    with col_ai2:
        st.caption("AI mapping analyzes column header text & data rows to auto-pair statement columns with Tally fields.")

    st.markdown("---")
    st.markdown("#### 🛠️ Statement Header Selection")

    mc1, mc2, mc3 = st.columns(3)

    with mc1:
        date_sel = st.selectbox("Date Column *", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("date")), help="Transaction Date (Required)")
        vdate_sel = st.selectbox("Value Date Column (Optional)", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("value_date")), help="Value Date (Optional, defaults to Date if skipped)")

    with mc2:
        narr_sel = st.selectbox("Description / Narration Column *", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("narration")), help="Narration / Particulars (Required)")
        chq_sel = st.selectbox("Cheque / Ref No Column (Optional)", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("cheque_no")), help="Cheque or Ref/UTR Number")

    with mc3:
        debit_sel = st.selectbox("Debit / Withdrawal Column *", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("debit")), help="Debit amount (Payment)")
        credit_sel = st.selectbox("Credit / Deposit Column *", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("credit")), help="Credit amount (Receipt)")
        bal_sel = st.selectbox("Balance Column (Optional)", options=header_options, index=get_option_idx(st.session_state.column_mapping.get("balance")), help="Running Balance")

    def parse_selected_idx(selected_text):
        if not selected_text or selected_text == "(None / Skip)":
            return None
        try:
            return int(selected_text.split('.')[0]) - 1
        except ValueError:
            return None

    if st.button("💾 Save Header Mapping"):
        st.session_state.column_mapping = {
            "date": parse_selected_idx(date_sel),
            "value_date": parse_selected_idx(vdate_sel),
            "narration": parse_selected_idx(narr_sel),
            "cheque_no": parse_selected_idx(chq_sel),
            "debit": parse_selected_idx(debit_sel),
            "credit": parse_selected_idx(credit_sel),
            "balance": parse_selected_idx(bal_sel)
        }
        st.session_state.use_custom_mapping = True
        st.success("Custom header mapping saved!")

# TAB 3: RULES MANAGER
with tab_rules:
    st.markdown("### 🎯 Narration -> Tally Ledger Mapping Rules")
    st.markdown("Define rules to automatically map transaction narrations to specific Tally Ledgers based on keywords or regex patterns.")

    rcol1, rcol2 = st.columns([2, 1])

    with rcol1:
        st.markdown("#### ➕ Add New Mapping Rule")
        with st.form("add_rule_form"):
            new_pattern = st.text_input("Narration Pattern / Keyword", placeholder="e.g. MANEESH or POS Rent or CEMTEX")
            new_ledger = st.text_input("Target Tally Ledger Name", placeholder="e.g. Maneesh Account or Bank Charges")
            new_match_type = st.selectbox("Match Type", ["contains", "exact", "regex"])

            submitted = st.form_submit_button("Add & Save Rule")
            if submitted:
                if new_pattern and new_ledger:
                    st.session_state.rules_engine.add_rule(new_pattern, new_ledger, new_match_type)
                    st.session_state.rules_engine.save_config(RULES_FILE)
                    st.success(f"Rule added! '{new_pattern}' -> '{new_ledger}'")
                    st.rerun()
                else:
                    st.error("Please provide both Pattern and Target Ledger Name.")

    with rcol2:
        st.markdown("#### ⚙️ Rule Configuration Options")
        if st.button("Reset to Default Rules"):
            st.session_state.rules_engine._load_default_rules()
            st.session_state.rules_engine.save_config(RULES_FILE)
            st.success("Reset to default rules!")
            st.rerun()

    st.markdown("#### 📜 Existing Active Rules")
    rules_list = st.session_state.rules_engine.rules

    if rules_list:
        rules_df = pd.DataFrame(rules_list)
        st.table(rules_df)
    else:
        st.info("No rules defined yet. Add your first rule above.")
