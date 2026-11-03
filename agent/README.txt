CyberPrint Pay - print agent (Windows Python)
==============================================

WHAT IT DOES
  Runs silently on the counter PC in the background. Every 3 seconds it checks Supabase for
  print requests submitted by customers. When a new job arrives:
    1. Sounds an audio alert chime.
    2. Sends a Windows 10/11 Action Center Toast notification.
    3. Displays an interactive floating notification card at the bottom-right of your screen:
         - Click "Print Nikalo (Y)" or press Enter/Y to print immediately.
         - Click "Reject Karo (N)" or press Esc/N to reject.
    4. Prints directly via native Windows GDI to your printer (PDF, JPG, PNG, BMP).
    5. No black terminal window required!

HOW TO RUN
  - start-agent.bat : Double-click to start the agent silently in the BACKGROUND.
  - stop-agent.bat  : Double-click to stop the background agent anytime.
  - run-agent.bat   : Double-click if you want to run in CONSOLE mode for debugging.

AUTO-START WITH WINDOWS (OPTIONAL)
  To start the background agent automatically when your PC boots:
    1. Press Win + R, type `shell:startup` and press Enter.
    2. Right-click `start-agent.bat`, click "Create shortcut", and paste the shortcut into that startup folder.

FILES
  agent.py          the Python print agent
  config.json       your settings (Supabase URL, anon key, operator email/password, printer name)
  start-agent.bat   starts background agent silently (no console window)
  stop-agent.bat    stops the background agent
  run-agent.bat     runs in terminal window (console mode)
  agent.log         execution logs and print history
