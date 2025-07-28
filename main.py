
import os
from pdf_processor import PDFProcessor

input_dir = "/app/input"
output_dir = "/app/output"

processor = PDFProcessor()

for filename in os.listdir(input_dir):
    if filename.endswith(".pdf"):
        input_path = os.path.join(input_dir, filename)
        output_filename = filename.replace(".pdf", ".json")
        output_path = os.path.join(output_dir, output_filename)
        
        with open(input_path, "rb") as f:
            result = processor.process_pdf(f)
        
        with open(output_path, "w", encoding="utf-8") as out_f:
            import json
            json.dump(result, out_f, indent=4, ensure_ascii=False)
