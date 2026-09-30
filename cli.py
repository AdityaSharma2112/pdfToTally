import argparse
import sys
import os
from bank_parser import SBIBankParser, detect_and_parse_pdf
from tally_xml_generator import TallyXMLGenerator
from rules_engine import NarrationRulesEngine

def main():
    parser = argparse.ArgumentParser(
        description="Convert Bank Statement PDF to Tally XML (Importable Vouchers)"
    )
    parser.add_argument("input_pdf", help="Path to input Bank Statement PDF file")
    parser.add_argument("-o", "--output", default="tally_import.xml", help="Output Tally XML file path")
    parser.add_argument("--company", default="Company Name", help="Current Company Name in Tally")
    parser.add_argument("--bank-ledger", default="State Bank of India", help="Bank Ledger Name in Tally")
    parser.add_argument("--party-ledger", default="SUSPENS", help="Default Party/Suspense Ledger Name")
    parser.add_argument("--rules-config", default="narration_rules.json", help="Path to narration-to-ledger mapping config JSON file")
    parser.add_argument("--start-voucher", type=int, default=1, help="Starting Voucher Number")

    args = parser.parse_args()

    if not os.path.exists(args.input_pdf):
        print(f"Error: File not found: {args.input_pdf}")
        sys.exit(1)

    # Load narration mapping rules
    rules_engine = None
    if os.path.exists(args.rules_config):
        print(f"Loading narration mapping rules from: {args.rules_config}")
        rules_engine = NarrationRulesEngine(args.rules_config)
    else:
        print("Using default narration mapping rules.")
        rules_engine = NarrationRulesEngine()

    print(f"Reading bank statement: {args.input_pdf}")
    metadata, transactions = detect_and_parse_pdf(args.input_pdf, rules_engine=rules_engine)

    print(f"Bank Detected: {metadata.get('bank_name', 'Unknown')}")
    print(f"Total Transactions Parsed: {len(transactions)}")

    if not transactions:
        print("Warning: No transactions were parsed from the PDF.")
        sys.exit(0)

    print("\nGenerating Tally XML...")
    generator = TallyXMLGenerator(
        company_name=args.company,
        bank_ledger=args.bank_ledger,
        default_counter_ledger=args.party_ledger
    )

    xml_content = generator.generate_xml(transactions, start_voucher_num=args.start_voucher)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"SUCCESS: Tally XML file saved to '{args.output}'!")
    print(f"You can now import '{args.output}' into Tally via: Import Data -> Vouchers")

if __name__ == "__main__":
    main()
