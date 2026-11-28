// CyberPrint Pay - configuration
// Fill the two Supabase values from your project: Settings -> API
window.CYBERPRINT_CONFIG = {
  SUPABASE_URL: "https://ejpepwflluoyqwfcheyn.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVqcGVwd2ZsbHVveXF3ZmNoZXluIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI3Mjk3MTUsImV4cCI6MjEwODMwNTcxNX0.fq6KW4wITCZDvI-AfgmGZJbFxntGzBWYbB-KX7AI2OI",

  SHOP_NAME: "Aapka Apna Cyber-café",

  // Public URL for customers accessing from mobile data (e.g. GitHub Pages or custom domain)
  // Customers can scan counter QR codes with 4G/5G mobile internet without needing shop Wi-Fi.
  PUBLIC_URL: "https://cyberphantomxpert.github.io/CyberPrint",

  // Pricing in rupees per printed side. Keep these the same as the
  // numbers inside supabase-setup.sql (the total is calculated there too).
  PRICE_BW: 5,
  PRICE_COLOR: 10,

  // Storage bucket that holds uploaded files
  BUCKET: "jobs",

  // Every uploaded file is deleted this many minutes after upload.
  RETENTION_MINUTES: 10,

  // Upload limits
  MAX_FILE_MB: 50,
  ALLOWED_TYPES: ["application/pdf", "image/jpeg", "image/png"],

  // Printer animation on the token screen (step 3).
  // The asset has two segments, read from its own markers:
  //   connect (frames 0-68)  loops while the operator has not approved yet
  //   print   (frames 68-179) loops once the job is printing
  PRINT_ANIM_ENABLED: true,
  ANIM_SPEED: 1.6,          // playback multiplier; 1.0 = 6s per page
  SECONDS_PER_SIDE: 3.75,   // keep in step with 6 / ANIM_SPEED for an honest bar
  PRINT_ANIM_MIN_MS: 2500   // hold the print loop at least this long
};
