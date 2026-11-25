export interface VoicePlaygroundScenario {
  id: string
  label: string
  languageCode: string
  ttsLang: string
  transcript: string
  intent: string
  emotionBadge: string
  safetyStatus: string
  gnaniTags: string[]
  thoughtProcess: string
  assistantReply: string
  speechTaggedReply: string
  extractedSlots: {
    policy_reference: string | null
    vehicle_type: string | null
    incident_location: string | null
    incident_date: string | null
    damage_description: string | null
  }
}

export interface ForensicsPlaygroundScenario {
  id: string
  label: string
  claimedCategory: string
  claimedPlate: string
  decision: 'PASS' | 'REVIEW' | 'REJECT'
  detectedCategory: string
  anprStatus: string
  anprDetectedPlate: string | null
  phashStatus: string
  provenanceNote: string
  decisionCodes: string[]
  yoloBoxes: Array<{ label: string; conf: string; top: string; left: string; width: string; height: string; kind: 'vehicle' | 'damage' }>
  preliminaryBand: string
}

export interface VehicleCostTierItem {
  id: string
  name: string
  category: 'Two-Wheeler (2W)' | 'Four-Wheeler (4W)'
  tierLabel: string
  multiplier: number
  sampleDamages: Array<{ part: string; basePart: number; labor: number; severityMultiplier: number }>
}

export interface LandingFaqItem {
  q: string
  a: string
}

export const VOICE_PLAYGROUND_SCENARIOS: VoicePlaygroundScenario[] = [
  {
    id: 'hinglish-skid',
    label: 'Hinglish 2W Skid',
    languageCode: 'hi-IN (Hinglish)',
    ttsLang: 'hi-IN',
    transcript:
      'Meri Activa KA 01 MJ 4412 kal shaam Indiranagar signal par baarish mein skid ho gayi, front mudguard aur headlamp toot gaya.',
    intent: 'claim_intake',
    emotionBadge: 'anxious_roadside',
    safetyStatus: 'urgent_safety_inquiry',
    gnaniTags: ['<slow>', '<pauses>'],
    thoughtProcess:
      'User suffered a wet-road 2-wheeler skid in Indiranagar. Check personal safety first, capture all 5 normalized English slots, and never re-ask given details.',
    assistantReply:
      'Indiranagar ke paas skid ke baare mein sunkar dukh hua — sabse pehle batayein aap bilkul safe toh hain na? Maine aapki Activa (KA-01-MJ-4412), kal shaam aur front mudguard/headlamp damage note kar liya hai.',
    speechTaggedReply:
      '<slow> Indiranagar ke paas skid ke baare mein sunkar dukh hua <pauses> sabse pehle batayein aap bilkul safe toh hain na? Maine aapki Activa KA-01-MJ-4412, kal shaam aur front mudguard aur headlamp damage note kar liya hai.',
    extractedSlots: {
      policy_reference: 'KA-01-MJ-4412',
      vehicle_type: 'Two-Wheeler (Scooter)',
      incident_location: 'Indiranagar, Bengaluru',
      incident_date: 'Yesterday Evening',
      damage_description: 'Front mudguard and headlamp broken.',
    },
  },
  {
    id: 'kanglish-truck',
    label: 'Kanglish High-Impact',
    languageCode: 'kn-IN (Kanglish)',
    ttsLang: 'kn-IN',
    transcript:
      'Whitefield main road nalli truck nanna bike KA 05 NB 7821 ge dikki hodeyitu, front fork bend aagide.',
    intent: 'claim_intake',
    emotionBadge: 'distressed_high_impact',
    safetyStatus: 'urgent_safety_inquiry',
    gnaniTags: ['<sigh>', '<pauses>', '<slow>'],
    thoughtProcess:
      'High-impact collision involving a truck and bent front fork. Prioritize injury check and advise against riding due to steering/fork damage.',
    assistantReply:
      'Whitefield hattira truck dikki keli tumba ghabari aayitu — modalu heli neevu kshemavaagiddira? Front fork bend aagirodrinda dayavittu bike chalayisabedi, towing arrange maadutteve.',
    speechTaggedReply:
      '<sigh> Whitefield hattira truck dikki keli tumba ghabari aayitu <pauses> <slow> modalu heli neevu kshemavaagiddira? Front fork bend aagirodrinda dayavittu bike chalayisabedi, towing arrange maadutteve.',
    extractedSlots: {
      policy_reference: 'KA-05-NB-7821',
      vehicle_type: 'Two-Wheeler (Bike)',
      incident_location: 'Whitefield Main Road, Bengaluru',
      incident_date: null,
      damage_description: 'Front fork bent (non-drivable caution).',
    },
  },
  {
    id: 'telugu-car',
    label: 'Telugu Car Claim',
    languageCode: 'te-IN (Telugu)',
    ttsLang: 'te-IN',
    transcript:
      'Hitech City daggara naa Swift car TS 09 UB 5510 ki rear auto hit ayyindi ninna evening, bumper dented.',
    intent: 'claim_intake',
    emotionBadge: 'calm_informative',
    safetyStatus: 'routine',
    gnaniTags: ['<slow>', '<pauses>'],
    thoughtProcess:
      'User reported rear auto impact in Telugu with plate TS-09-UB-5510 and bumper dent. Acknowledge captured details and proceed to Stage 5 live camera capture.',
    assistantReply:
      'Mee Swift car (TS-09-UB-5510) Hitech City incident mariyu rear bumper dent vivaralu English lo note chesanu. Ippudu live camera tho license plate mariyu damage photo capture cheyandi.',
    speechTaggedReply:
      '<slow> Mee Swift car TS-09-UB-5510 Hitech City incident mariyu rear bumper dent vivaralu note chesanu <pauses> ippudu live camera tho license plate mariyu damage photo capture cheyandi.',
    extractedSlots: {
      policy_reference: 'TS-09-UB-5510',
      vehicle_type: 'Four-Wheeler (Car)',
      incident_location: 'Hitech City, Hyderabad',
      incident_date: 'Yesterday Evening',
      damage_description: 'Rear bumper dented.',
    },
  },
  {
    id: 'hindi-greeting',
    label: 'Hindi Greeting Guard',
    languageCode: 'hi-IN (Devanagari)',
    ttsLang: 'hi-IN',
    transcript: 'हलो। क्या आपको मेरी आवाज़ आ रही है?',
    intent: 'greeting',
    emotionBadge: 'warm_friendly',
    safetyStatus: 'routine',
    gnaniTags: ['<excited>', '<pauses>'],
    thoughtProcess:
      'User only greeted and tested their mic. Zero accident script triggered; damage_description remains strictly null.',
    assistantReply:
      'नमस्ते! जी हाँ, आपकी आवाज़ बिल्कुल साफ़ आ रही है। बताइए, आज मैं आपकी मोटर क्लेम में किस प्रकार सहायता कर सकता हूँ?',
    speechTaggedReply:
      '<excited> नमस्ते! जी हाँ, आपकी आवाज़ बिल्कुल साफ़ आ रही है। <pauses> बताइए, आज मैं आपकी मोटर क्लेम में किस प्रकार सहायता कर सकता हूँ?',
    extractedSlots: {
      policy_reference: null,
      vehicle_type: null,
      incident_location: null,
      incident_date: null,
      damage_description: null,
    },
  },
]

export const FORENSICS_PLAYGROUND_SCENARIOS: ForensicsPlaygroundScenario[] = [
  {
    id: 'pass-2w',
    label: 'Valid 2W Live Capture (PASS)',
    claimedCategory: 'Two-Wheeler (Bike)',
    claimedPlate: 'KA-01-MJ-4412',
    decision: 'PASS',
    detectedCategory: 'Two-Wheeler (94% conf)',
    anprStatus: 'MATCHED',
    anprDetectedPlate: 'KA-01-MJ-4412',
    phashStatus: 'Unique · Hamming Dist > 24 (No Cross-Claim Reuse)',
    provenanceNote: 'Advisory Signal: Camera EXIF intact · Verified via Stage 5 Live Session CAP-2026',
    decisionCodes: ['STAGE_1_MAGIC_BYTES_OK', 'ANPR_PLATE_MATCHED', 'YOLOV8_2W_DAMAGE_CONFIRMED'],
    yoloBoxes: [
      { label: 'motorcycle 94%', conf: '94%', top: '14%', left: '12%', width: '76%', height: '72%', kind: 'vehicle' },
      { label: 'broken_headlamp 89%', conf: '89%', top: '24%', left: '22%', width: '22%', height: '24%', kind: 'damage' },
      { label: 'broken_fairing 84%', conf: '84%', top: '44%', left: '34%', width: '28%', height: '26%', kind: 'damage' },
    ],
    preliminaryBand: '₹4,120 – ₹5,820 (2W Standard Tier)',
  },
  {
    id: 'reject-mismatch',
    label: 'Car Photo on Bike Policy (REJECT)',
    claimedCategory: 'Two-Wheeler (Bike)',
    claimedPlate: 'KA-01-MJ-4412',
    decision: 'REJECT',
    detectedCategory: 'Four-Wheeler (Car) · 96% conf',
    anprStatus: 'NOT_APPLICABLE (Rejected Stage 3)',
    anprDetectedPlate: null,
    phashStatus: 'Checked · 64-bit DCT Indexed',
    provenanceNote: 'Close-up 4W panel detected by symmetric CarDD vs. Bike guard',
    decisionCodes: ['VEHICLE_CATEGORY_MISMATCH', 'CLAIMED_TWO_WHEELER_DETECTED_CAR'],
    yoloBoxes: [
      { label: 'car_bumper_closeup 96%', conf: '96%', top: '12%', left: '10%', width: '80%', height: '76%', kind: 'vehicle' },
      { label: 'scratch 87%', conf: '87%', top: '34%', left: '18%', width: '36%', height: '22%', kind: 'damage' },
    ],
    preliminaryBand: '₹0 (Blocked — Wizard Step 3 Prevented)',
  },
  {
    id: 'review-plate',
    label: 'Swapped License Plate (REVIEW)',
    claimedCategory: 'Four-Wheeler (Car)',
    claimedPlate: 'KA-01-MJ-4412',
    decision: 'REVIEW',
    detectedCategory: 'Four-Wheeler (Car) · 92% conf',
    anprStatus: 'MISMATCH_FLAGGED',
    anprDetectedPlate: 'MH-12-DE-9999',
    phashStatus: 'Unique · Live Camera Token Verified',
    provenanceNote: 'Physical plate read via Gemini Vision ANPR conflicts with insured vehicle',
    decisionCodes: ['VEHICLE_REGISTRATION_PLATE_MISMATCH', 'ESCALATED_FOR_ADJUSTER_REVIEW'],
    yoloBoxes: [
      { label: 'car 92%', conf: '92%', top: '10%', left: '10%', width: '80%', height: '78%', kind: 'vehicle' },
      { label: 'plate: MH-12-DE-9999', conf: '98%', top: '60%', left: '36%', width: '28%', height: '13%', kind: 'damage' },
    ],
    preliminaryBand: 'Provisional Band Held Pending Adjuster Sign-Off',
  },
]

export const VEHICLE_COST_TIERS: VehicleCostTierItem[] = [
  {
    id: 'splendor',
    name: 'Hero Splendor Plus',
    category: 'Two-Wheeler (2W)',
    tierLabel: '2W Commuter Tier',
    multiplier: 0.85,
    sampleDamages: [
      { part: 'Front Headlamp Assembly', basePart: 1800, labor: 350, severityMultiplier: 1.5 },
      { part: 'Front Fairing / Mudguard', basePart: 2200, labor: 500, severityMultiplier: 1.0 },
    ],
  },
  {
    id: 'activa',
    name: 'Honda Activa 6G',
    category: 'Two-Wheeler (2W)',
    tierLabel: '2W Standard / Scooter Tier',
    multiplier: 1.0,
    sampleDamages: [
      { part: 'Front Headlamp Assembly', basePart: 1800, labor: 350, severityMultiplier: 1.5 },
      { part: 'Side Body Panel / Fairing', basePart: 2200, labor: 500, severityMultiplier: 1.5 },
    ],
  },
  {
    id: 'classic350',
    name: 'Royal Enfield Classic 350',
    category: 'Two-Wheeler (2W)',
    tierLabel: '2W Premium / Cruiser Tier',
    multiplier: 1.45,
    sampleDamages: [
      { part: 'Front Headlamp & Casing', basePart: 1800, labor: 350, severityMultiplier: 1.5 },
      { part: 'Fuel Tank Dent & Paint', basePart: 1200, labor: 400, severityMultiplier: 2.2 },
    ],
  },
  {
    id: 'swift',
    name: 'Maruti Suzuki Swift',
    category: 'Four-Wheeler (4W)',
    tierLabel: '4W Compact Hatchback Tier',
    multiplier: 1.0,
    sampleDamages: [
      { part: 'Bumper Crack & Repaint', basePart: 3500, labor: 1000, severityMultiplier: 1.5 },
      { part: 'Headlamp Assembly', basePart: 4000, labor: 600, severityMultiplier: 1.0 },
    ],
  },
  {
    id: 'creta',
    name: 'Hyundai Creta',
    category: 'Four-Wheeler (4W)',
    tierLabel: '4W Midsize SUV Tier',
    multiplier: 1.45,
    sampleDamages: [
      { part: 'Bumper Crack & Sensor Alignment', basePart: 3500, labor: 1000, severityMultiplier: 1.5 },
      { part: 'LED Headlamp Broken', basePart: 4000, labor: 600, severityMultiplier: 1.5 },
    ],
  },
  {
    id: 'xuv700',
    name: 'Mahindra XUV700',
    category: 'Four-Wheeler (4W)',
    tierLabel: '4W Premium SUV / Flagship Tier',
    multiplier: 2.25,
    sampleDamages: [
      { part: 'ADAS Bumper & Crack Repair', basePart: 3500, labor: 1000, severityMultiplier: 1.5 },
      { part: 'Matrix LED Lamp Broken', basePart: 4000, labor: 600, severityMultiplier: 1.5 },
    ],
  },
]

export const LANDING_FAQS: LandingFaqItem[] = [
  {
    q: 'Why does ClaimSathi block raw WhatsApp photos and send a 1-tap browser handoff instead?',
    a: 'WhatsApp recompresses photos and strips EXIF, GPS, and C2PA metadata on 100% of uploads. ClaimSathi uses WhatsApp strictly for convenient voice-note intake and notifications, then dispatches a single-use 48-bit tokenized link that opens our Stage 5 Live Camera directly in the mobile browser with gallery uploads blocked.',
  },
  {
    q: 'Do you rely on C2PA or SynthID watermarks to prove a claim photo is genuine?',
    a: 'No. We treat C2PA and SynthID strictly as advisory risk signals—we flag if an AI watermark is found, but never trust the absence of a watermark as proof of authenticity. Our primary anti-fraud shield is Stage 5 Guided Live Capture, pixel-level ANPR plate matching, and 64-bit DCT pHash cross-claim duplicate screening.',
  },
  {
    q: 'How does ClaimSathi prevent swapped-vehicle fraud inside the same vehicle category?',
    a: 'Beyond our symmetric Car-vs-Bike guard, Stage 5 mandates capturing the vehicle registration plate, odometer/VIN, and RC/DL. Pixel ANPR OCR extracts the physical license plate from the live frame and automatically flags VEHICLE_REGISTRATION_PLATE_MISMATCH for adjuster review if it differs from the insured policy.',
  },
  {
    q: 'Are AI cost estimates guaranteed payouts?',
    a: 'Never. Every estimate is explicitly labeled as a Preliminary AI Repair Cost Band (Min–Max INR) calibrated across India’s top 2W & 4W make/model tiers for licensed surveyor/adjuster review. Under IRDAI guidelines, final coverage liability and settlement rest solely with the insurer/TPA.',
  },
  {
    q: 'How are DPDP Rules 2025 and IRDAI 2026 AI governance handled?',
    a: 'We capture unbundled, purpose-specific consent before voice or camera recording, mask PII (phone & registration numbers) in operational logs, support one-click consent-withdrawal media erasure with 1-year statutory audit retention, and track adjuster override reason tags to measure AI false-positive rates separately.',
  },
]
