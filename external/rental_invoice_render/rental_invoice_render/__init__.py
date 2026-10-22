from collections.abc import Mapping
from pathlib import Path


def render_invoice(invoice: Mapping[str, object], output_path: Path) -> Path:
    content = "Rental invoice\n"
    content += "\n".join(f"{field}: {value}" for field, value in invoice.items())
    output_path.write_text(content + "\n", encoding="utf-8")
    return output_path
