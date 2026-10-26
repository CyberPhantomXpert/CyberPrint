# CyberPrint Pay — Kiosk & Mobile Self-Service Printing

Fast, private, self-service counter printing system designed for Indian cyber cafes, print shops, and stationery stores.

## Features
- **Customer Mobile Portal (`index.html`)**: Customers scan a counter QR code, select files (PDF, JPG, PNG), configure print settings (Copies, B&W vs Color, Page Range), pay via UPI, and receive an instant Job Token.
- **Operator Desk (`admin.html`)**: Shopkeeper dashboard with real-time queue management, audio alerts, daily revenue & page count counters, and direct 1-tap mobile printing.
- **Native GDI Print Agent (`agent/agent.py`)**: Runs silently in the background on the counter PC with zero terminal windows, native Windows Action Center Toast notifications, and automatic high-speed pigment black hardware optimization for Canon MegaTank printers.
- **PWA Mobile Install**: Can be installed on Android & iOS home screens as a standalone native app.

## Quick Start
1. Edit `config.js` and `agent/config.json` with your Supabase credentials and UPI ID.
2. In your Supabase SQL editor, run `supabase-setup.sql` once.
3. Host `index.html`, `admin.html`, `config.js`, `manifest.json`, and `sw.js` on GitHub Pages.
4. On the counter PC connected to the printer, double-click `agent/start-agent.bat`.
