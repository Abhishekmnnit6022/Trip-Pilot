"""
TripPilot — Professional PDF Expense Report Generator

Generates a branded, beautifully formatted PDF summarizing all expenses
for a completed trip. The PDF includes:
  - TripPilot logo and header
  - Trip summary (name, dates, total cost)
  - Itemized booking table (flights, trains, hotels)
  - Category-wise expense breakdown

Uses fpdf2 for lightweight, dependency-free PDF generation.
"""

import os
import io
import logging
from datetime import datetime
from fpdf import FPDF

log = logging.getLogger(__name__)

# Resolve logo path relative to this file's parent (project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGO_PATH = os.path.join(_PROJECT_ROOT, "logo.png")


class TripReport(FPDF):
    """Custom PDF class with TripPilot branding."""

    def header(self):
        """Render branded header with logo on every page."""
        # Clean white header background
        self.set_fill_color(255, 255, 255)
        self.rect(0, 0, 210, 42, "F")

        # Teal accent stripe at the bottom of the header
        self.set_fill_color(94, 172, 163)  # Matches logo teal
        self.rect(0, 42, 210, 2, "F")

        # Logo handling — logo has dark navy + teal on white/transparent bg
        if os.path.exists(_LOGO_PATH):
            try:
                self.image(_LOGO_PATH, x=12, y=6, h=30)
            except Exception:
                self._render_text_fallback()
        else:
            self._render_text_fallback()

        # Tagline below logo
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(120, 140, 155)
        self.set_xy(12, 36)
        self.cell(80, 8, "AI-Powered Travel Planning", align="L")

        self.ln(35)
        
    def _render_text_fallback(self):
        """Fallback header text if logo is missing."""
        self.set_font("Helvetica", "B", 24)
        self.set_text_color(15, 23, 42)  # Dark navy text on white bg
        self.set_xy(15, 12)
        self.cell(0, 10, "TripPilot", align="L")

        self.set_font("Helvetica", "", 10)
        self.set_text_color(94, 172, 163)  # Teal
        self.set_xy(15, 22)
        self.cell(0, 10, "AI-Powered Travel Planning Platform", align="L")

    def footer(self):
        """Render page number footer."""
        self.set_y(-20)
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y(), 200, self.get_y())
        
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}  |  Generated securely by TripPilot", align="C")


def _safe_price(details: dict) -> float:
    """Extract a numeric price from a booking details dict."""
    price = details.get("amount_paid") or details.get("price") or 0
    if isinstance(price, (int, float)):
        return float(price)
    if isinstance(price, str):
        cleaned = price.replace(",", "").replace("₹", "").replace("Rs", "").replace("INR", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def generate_trip_report(
    trip_name: str,
    traveler_name: str,
    bookings: list[dict],
    custom_expenses: list[dict] = None,
    trip_created: str = "",
    trip_completed: str = "",
) -> bytes:
    """
    Generate a professional PDF expense report for a completed trip.
    """
    pdf = TripReport()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── Trip Title ────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 12, "Official Expense Report", ln=True, align="C")
    
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 6, trip_name, ln=True, align="C")
    pdf.ln(6)

    # ── Trip Info Box (Sleek Card Style) ──────────────────────────────────
    pdf.set_fill_color(248, 250, 252) # Very light gray/blue
    pdf.set_draw_color(226, 232, 240) # Slate 200
    pdf.rect(15, pdf.get_y(), 180, 28, "DF")

    y_start = pdf.get_y() + 4
    
    # Parse dates
    created_str = "N/A"
    completed_str = "N/A"
    try:
        if trip_created:
            dt = datetime.fromisoformat(str(trip_created).replace("Z", "+00:00"))
            created_str = dt.strftime("%d %b %Y")
    except Exception:
        pass
    try:
        if trip_completed:
            dt = datetime.fromisoformat(str(trip_completed).replace("Z", "+00:00"))
            completed_str = dt.strftime("%d %b %Y")
    except Exception:
        pass

    # Left Column
    pdf.set_xy(20, y_start)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(20, 6, "Traveler: ", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(65, 6, traveler_name, ln=False)

    # Right Column
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 6, "Trip Name: ", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(55, 6, trip_name[:30], ln=True, align="R")

    # Left Column Row 2
    pdf.set_xy(20, y_start + 8)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(20, 6, "Started: ", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(65, 6, created_str, ln=False)

    # Right Column Row 2
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 6, "Completed: ", ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(55, 6, completed_str, ln=True, align="R")

    pdf.set_xy(20, y_start + 16)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 6, "Total Bookings: ", ln=False)
    pdf.set_font("Helvetica", "", 10)
    
    custom_len = len(custom_expenses) if custom_expenses else 0
    pdf.cell(55, 6, f"{len(bookings)} (plus {custom_len} custom expenses)", ln=True)

    pdf.set_y(pdf.get_y() + 12)

    # ── Categorize bookings ───────────────────────────────────────────────
    total_cost = 0.0
    category_totals = {"Flights": 0.0, "Trains": 0.0, "Hotels": 0.0}

    # ── Booking Table ─────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 10, "Itemized Expenses", ln=True)

    # Table header
    col_widths = [10, 55, 30, 45, 20, 20]
    headers = ["#", "Provider", "Type", "PNR / Booking ID", "Date", "Cost"]
    
    pdf.set_fill_color(15, 23, 42) # Dark navy header for high contrast
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)

    for i, h in enumerate(headers):
        align = "C" if i != 1 else "L"
        if i == 5: align = "R"
        pdf.cell(col_widths[i], 10, h, border=0, fill=True, align=align)
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)

    all_bookings = bookings
    for idx, b in enumerate(all_bookings, start=1):
        details = b.get("details") or {}
        price = _safe_price(details)
        total_cost += price

        b_type = (b.get("booking_type") or "other").title()
        if b_type == "Flight":
            category_totals["Flights"] += price
        elif b_type == "Train":
            category_totals["Trains"] += price
        elif b_type == "Hotel":
            category_totals["Hotels"] += price

        pnr = b.get("pnr_or_confirmation_number", "N/A")
        # Format date nicer if possible
        raw_date = str(b.get("travel_date") or "")
        travel_date = "TBD"
        if raw_date:
            try:
                travel_date = datetime.fromisoformat(raw_date).strftime("%d %b")
            except:
                travel_date = raw_date

        provider = b.get("provider_name", "N/A")

        # Alternate row colors
        if idx % 2 == 0:
            pdf.set_fill_color(241, 245, 249)
            fill = True
        else:
            fill = False

        type_display = b_type
        cost_display = f"Rs.{price:,.0f}" if price > 0 else "N/A"

        # Taller rows for better readability
        row_height = 9
        pdf.set_draw_color(226, 232, 240)
        
        pdf.cell(col_widths[0], row_height, str(idx), border="B", fill=fill, align="C")
        pdf.cell(col_widths[1], row_height, " " + provider[:35], border="B", fill=fill, align="L")
        pdf.cell(col_widths[2], row_height, type_display, border="B", fill=fill, align="C")
        pdf.cell(col_widths[3], row_height, pnr, border="B", fill=fill, align="C")
        pdf.cell(col_widths[4], row_height, travel_date, border="B", fill=fill, align="C")
        pdf.cell(col_widths[5], row_height, cost_display + " ", border="B", fill=fill, align="R")
        pdf.ln()

    # Total row for bookings
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_text_color(15, 23, 42)
    total_w = sum(col_widths[:-1])
    pdf.cell(total_w, 12, "BOOKINGS TOTAL  ", border=0, fill=True, align="R")
    pdf.set_text_color(15, 23, 42) 
    pdf.cell(col_widths[-1], 12, f"Rs.{total_cost:,.0f} ", border=0, fill=True, align="R")
    pdf.ln(15)

    # ── Custom Expenses Table (If any) ────────────────────────────────────
    if custom_expenses:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 10, "Custom Tracked Expenses", ln=True)

        ce_col_widths = [10, 85, 35, 40]
        ce_headers = ["#", "Description", "Category", "Cost"]
        
        pdf.set_fill_color(15, 23, 42)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)

        for i, h in enumerate(ce_headers):
            align = "L" if i == 1 else "C"
            if i == 3: align = "R"
            pdf.cell(ce_col_widths[i], 10, h, border=0, fill=True, align=align)
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(51, 65, 85)
        
        ce_total = 0.0
        for idx, ce in enumerate(custom_expenses, start=1):
            amt = float(ce.get("amount", 0))
            ce_total += amt
            total_cost += amt
            
            cat = ce.get("category", "Other")
            if cat not in category_totals:
                category_totals[cat] = 0.0
            category_totals[cat] += amt
            
            fill = (idx % 2 == 0)
            if fill:
                pdf.set_fill_color(241, 245, 249)
                
            pdf.set_draw_color(226, 232, 240)
            pdf.cell(ce_col_widths[0], 9, str(idx), border="B", fill=fill, align="C")
            pdf.cell(ce_col_widths[1], 9, " " + ce.get("description", "")[:60], border="B", fill=fill, align="L")
            pdf.cell(ce_col_widths[2], 9, cat, border="B", fill=fill, align="C")
            pdf.cell(ce_col_widths[3], 9, f"Rs.{amt:,.0f} ", border="B", fill=fill, align="R")
            pdf.ln()
            
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(241, 245, 249)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(sum(ce_col_widths[:-1]), 12, "CUSTOM EXPENSES TOTAL  ", border=0, fill=True, align="R")
        pdf.cell(ce_col_widths[-1], 12, f"Rs.{ce_total:,.0f} ", border=0, fill=True, align="R")
        pdf.ln(15)

    # ── Grand Total ───────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_fill_color(15, 23, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(150, 12, "GRAND TOTAL TRIP COST  ", border=0, fill=True, align="R")
    pdf.set_text_color(56, 189, 248) # Sky blue text for the grand total
    pdf.cell(40, 12, f"Rs.{total_cost:,.0f}  ", border=0, fill=True, align="R")
    pdf.ln(15)

    # ── Category Breakdown ────────────────────────────────────────────────
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Category Breakdown", ln=True)
    pdf.ln(2)

    bar_max_width = 110
    for cat, amount in category_totals.items():
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(71, 85, 105)
        pct = (amount / total_cost * 100) if total_cost > 0 else 0
        pdf.cell(25, 8, f"{cat}", ln=False)

        # Draw bar
        bar_width = (amount / total_cost * bar_max_width) if total_cost > 0 else 0
        y = pdf.get_y() + 1.5
        x = pdf.get_x()

        # Bar background
        pdf.set_fill_color(241, 245, 249)
        pdf.rect(x, y, bar_max_width, 6, "F")

        # Bar fill (Premium colors)
        color_map = {"Flights": (56, 189, 248), "Trains": (52, 211, 153), "Hotels": (251, 146, 60), "Itinerary Activity": (167, 139, 250), "Food": (244, 114, 182), "Other": (148, 163, 184)}
        r, g, b_c = color_map.get(cat, (100, 100, 100))
        pdf.set_fill_color(r, g, b_c)
        if bar_width > 0:
            pdf.rect(x, y, bar_width, 6, "F")

        pdf.set_xy(x + bar_max_width + 5, pdf.get_y())
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, f"Rs.{amount:,.0f}  ({pct:.0f}%)", ln=True)
        pdf.ln(2)

    pdf.ln(15)

    # ── Footer note ───────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 6, f"This report was generated securely by TripPilot on {datetime.now().strftime('%d %b %Y')}.", ln=True, align="C")
    pdf.cell(0, 6, "Thank you for traveling with us. Wishing you safe journeys ahead!", ln=True, align="C")

    # Return bytes
    return pdf.output()
