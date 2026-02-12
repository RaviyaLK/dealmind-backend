import pandas as pd
from pathlib import Path
from typing import Tuple
from sqlalchemy.orm import Session
from app.models.employee import Employee
import uuid


class ExcelProcessor:
    """Process Excel files for employee data import."""

    # Expected column mappings (flexible - maps various header names to our fields)
    COLUMN_MAPPINGS = {
        "name": ["name", "full_name", "employee_name", "full name", "employee"],
        "email": ["email", "email_address", "e-mail", "mail"],
        "role": ["role", "title", "job_title", "position", "job title"],
        "department": ["department", "dept", "team", "division"],
        "skills": ["skills", "skill_set", "competencies", "expertise", "skill set"],
        "availability_percent": [
            "availability", "availability_percent", "avail", "available",
            "availability %", "availability (%)", "availability(%)",
        ],
        "hourly_rate": [
            "hourly_rate", "rate", "hourly rate", "cost_rate", "cost rate",
            "$/hr", "hourly rate ($)", "hourly rate($)", "rate ($)", "rate($)",
        ],
    }

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize a column header: lowercase, strip, remove parenthesized units."""
        import re
        text = text.lower().strip()
        # Remove parenthesized content like "(%)" or "($)" for fuzzy matching
        text_stripped = re.sub(r'\s*\([^)]*\)', '', text).strip()
        return text_stripped

    def _find_column(self, df_columns: list, field: str) -> str | None:
        """Find matching column name from dataframe."""
        possible_names = self.COLUMN_MAPPINGS.get(field, [field])
        # First pass: exact match (lowered & stripped)
        for col in df_columns:
            if col.lower().strip() in possible_names:
                return col
        # Second pass: match after stripping parenthesized units like (%) ($)
        for col in df_columns:
            normalized = self._normalize(col)
            if normalized in possible_names:
                return col
        return None

    def process_employee_excel(
        self, file_path: str, db: Session, filename: str
    ) -> Tuple[int, int, list[str]]:
        """
        Process an Excel file and import employees into the database.
        Returns (imported_count, skipped_count, errors).
        """
        try:
            df = pd.read_excel(file_path, engine="openpyxl")
        except Exception as e:
            return 0, 0, [f"Failed to read Excel file: {str(e)}"]

        if df.empty:
            return 0, 0, ["Excel file is empty"]

        # Normalize column names
        df.columns = [str(col).strip() for col in df.columns]
        col_map = {}
        for field in self.COLUMN_MAPPINGS:
            matched = self._find_column(list(df.columns), field)
            if matched:
                col_map[field] = matched

        if "name" not in col_map:
            return 0, 0, ["Could not find a 'name' column in the Excel file"]

        imported = 0
        skipped = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                name = str(row.get(col_map.get("name", ""), "")).strip()
                if not name or name == "nan":
                    skipped += 1
                    continue

                email = str(row.get(col_map.get("email", ""), "")).strip()
                if email == "nan":
                    email = ""

                # Check for duplicate by email
                if email and db.query(Employee).filter(Employee.email == email).first():
                    skipped += 1
                    continue

                # Parse skills - could be comma-separated string
                skills_raw = row.get(col_map.get("skills", ""), "")
                if isinstance(skills_raw, str) and skills_raw != "nan":
                    skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
                else:
                    skills = []

                # Parse availability
                avail = row.get(col_map.get("availability_percent", ""), 100)
                try:
                    avail = int(float(str(avail).replace("%", "")))
                except (ValueError, TypeError):
                    avail = 100

                # Parse hourly rate
                rate = row.get(col_map.get("hourly_rate", ""), 0)
                try:
                    rate = float(str(rate).replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    rate = 0.0

                employee = Employee(
                    id=str(uuid.uuid4()),
                    name=name,
                    email=email if email else f"{name.lower().replace(' ', '.')}@company.com",
                    role=str(row.get(col_map.get("role", ""), "Unknown")).strip(),
                    department=str(row.get(col_map.get("department", ""), "General")).strip(),
                    skills=skills,
                    availability_percent=max(0, min(100, avail)),
                    hourly_rate=rate,
                    is_active=True,
                    uploaded_from=filename,
                )
                db.add(employee)
                imported += 1

            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                skipped += 1

        if imported > 0:
            db.commit()

        return imported, skipped, errors


excel_processor = ExcelProcessor()
