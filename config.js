// CyberPrint Pay - configuration
// Fill the two Supabase values from your project: Settings -> API
window.CYBERPRINT_CONFIG = {
  SUPABASE_URL: "https://ejpepwflluoyqwfcheyn.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVqcGVwd2ZsbHVveXF3ZmNoZXluIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI3Mjk3MTUsImV4cCI6MjEwODMwNTcxNX0.fq6KW4wITCZDvI-AfgmGZJbFxntGzBWYbB-KX7AI2OI",

  SHOP_NAME: "Aapka Apna Cyber-café",

  // UPI payment details - used to build the payment QR and the "Pay" button.
  UPI_ID: "ankitsingh953431@okaxis",
  UPI_NAME: "Ankit Singh",

  // Pricing in rupees per printed side. Keep these the same as the
  // numbers inside supabase-setup.sql (the total is calculated there too).
  PRICE_BW: 5,
  PRICE_COLOR: 10,

  // Storage bucket that holds uploaded files
  BUCKET: "jobs",

  // Every uploaded file is deleted this many minutes after upload.
  RETENTION_MINUTES: 10,

  // Upload limits
  MAX_FILE_MB: 20,
  ALLOWED_TYPES: ["application/pdf", "image/jpeg", "image/png"]
};

