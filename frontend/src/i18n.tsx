import React, { createContext, useContext, useState, useEffect } from 'react'

export type AppLanguageCode = 'en' | 'kn' | 'te' | 'hi' | 'ta'

export const APP_LANGUAGES: { code: AppLanguageCode; label: string; native: string }[] = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'kn', label: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'te', label: 'Telugu', native: 'తెలుగు' },
  { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
  { code: 'ta', label: 'Tamil', native: 'தமிழ்' },
]

const TRANSLATIONS: Record<AppLanguageCode, Record<string, string>> = {
  en: {
    nav_vault: 'Customer Claims Vault',
    nav_new_claim: 'New Claim Wizard',
    nav_settings: 'Settings & Profile',
    nav_sign_out: 'Sign Out',
    app_lang_label: 'App Language',
    // Wizard Stepper
    step1_title: '1. Multilingual AI Intake',
    step1_sub: 'Steps 2–4: Voice/Text & Follow-ups',
    step2_title: '2. Evidence & Integrity Engine',
    step2_sub: 'Steps 5–6: Live Camera, C2PA & pHash',
    step3_title: '3. Review & Generate Dossier',
    step3_sub: 'Steps 7–9: 9-Section Report & Gateway',
    // Step 1 Header & Controls
    step1_heading: 'Step 1: Multilingual Conversational Claim Intake',
    step1_desc:
      'Speak in Kannada, Telugu, Hindi, Tamil, or English — AI automatically fills all insurer fields in English.',
    speak_claim_btn: 'Speak Your Claim (Press to Talk)',
    upload_audio_btn: 'Upload Audio File',
    type_placeholder:
      'Or type your accident explanation in Kannada, Telugu, Hindi, or English...',
    extract_btn: 'Extract',
    speak_answer_btn: '🎙️ Speak Answer',
    done_speaking_btn: 'Done Speaking',
    cancel_btn: 'Cancel',
    reset_btn: 'Reset',
    next_evidence_btn: 'Next: Evidence Screening',
    continue_step2_btn: 'Continue to Step 2: Upload & Screen Evidence',
    // Extracted Claim Fields HUD
    extracted_fields_title: 'Extracted Claim Fields (Insurer Format: English)',
    extracted_fields_sub: 'Spoken in any Indian language → Auto-normalized to English for Insurer',
    captured_badge: 'Captured',
    field_policy_reference: 'Policy / Vehicle Number',
    field_vehicle_type: 'Vehicle Type',
    field_incident_location: 'Incident Location',
    field_incident_date: 'Incident Date & Time',
    field_damage_description: 'Damage Description',
    all_captured_banner:
      'All 5 core claim fields captured in English! Proceed to Evidence & Live Camera Screening.',
    answering_followup: 'Answering Follow-Up',
    // Dashboard
    vault_title: 'Customer Claims Vault & Dossier Center',
    vault_subtitle:
      'Manage your motor insurance claims, cryptographic evidence screening, and 9-section insurer dossiers.',
    start_new_claim: 'Start New Claim Intake',
    // Claim Detail & Report Download
    report_lang_label: 'Report Language:',
    download_preferred_lang_btn: 'Print / Download in Preferred Language',
    download_english_pdf_btn: 'Official English PDF (For Insurer)',
    download_json_btn: 'Canonical JSON',
    submit_insurer_btn: 'Submit to Insurer Gateway',
    // Settings Modal
    settings_title: 'Settings, Profile & App Language',
    settings_tab_lang: 'App Language & Voice',
    settings_tab_profile: 'Customer Profile & Policy',
    choose_app_lang: 'Choose App Display Language (Website Text Language)',
    choose_app_lang_desc:
      'Changes all buttons, menus, and instructions across ClaimSathi AI into your preferred reading language. Claim values sent to insurance companies remain in English.',
    choose_report_lang: 'Default Report Download Language',
    choose_voice_mode: 'Default Voice Recognition Mode',
    save_settings_btn: 'Save Preferences',
    close_btn: 'Close',
    // Login Screen
    login_badge: 'IRDAI-Aligned Motor Insurance Intake',
    login_title: 'ClaimSathi AI',
    login_subtitle: 'Secure Customer Claims Vault & Conversational Intake',
    login_tab_signin: 'Sign In to Vault',
    login_tab_register: 'Create Account',
    login_id_label: 'Email, Phone Number, or Customer ID',
    login_id_placeholder: 'e.g. rahul.sharma@claimsathi.in or USR-100001',
    login_pwd_label: 'Password',
    login_pwd_placeholder: 'Enter your account password',
    login_otp_toggle_to_otp: 'Sign in with OTP instead',
    login_otp_toggle_to_pwd: 'Sign in with Password instead',
    login_otp_label: '6-Digit Verification OTP',
    login_otp_placeholder: 'Enter 6-digit OTP',
    login_otp_send_btn: 'Send OTP',
    login_submit_btn: 'Sign In to Customer Claims Vault',
    login_quick_demo_title: 'Demo Test Accounts (Click to Auto-Fill):',
    // Claim Detail Screen
    claim_detail_back: 'Back to Claims Vault',
    claim_detail_dossier_title: 'Official Motor Insurance Claim Dossier',
    claim_detail_dossier_subtitle: 'Cryptographically Verified 9-Section Claims Package',
    claim_detail_tab_summary: 'Dossier Summary',
    claim_detail_tab_evidence: 'Evidence & Integrity Engine',
    claim_detail_tab_audit: 'Audit & Provenance Trail',
    claim_detail_tab_raw: 'Raw Layer-1 JSON',
  },
  kn: {
    nav_vault: 'ಗ್ರಾಹಕರ ಕ್ಲೈಮ್ ವಾಲ್ಟ್',
    nav_new_claim: 'ಹೊಸ ಕ್ಲೈಮ್ ನೋಂದಣಿ',
    nav_settings: 'ಸೆಟ್ಟಿಂಗ್ಸ್ ಮತ್ತು ಪ್ರೊಫೈಲ್',
    nav_sign_out: 'ಲಾಗ್ ಔಟ್',
    app_lang_label: 'ಆಪ್ ಭಾಷೆ',
    step1_title: '1. ಬಹುಭಾಷಾ AI ಮಾಹಿತಿ ಸಂಗ್ರಹ',
    step1_sub: 'ಹಂತ 2–4: ಧ್ವನಿ / ಪಠ್ಯ ಸಂಭಾಷಣೆ',
    step2_title: '2. ಸಾಕ್ಷ್ಯಾಧಾರ ಮತ್ತು ಪರಿಶೀಲನೆ',
    step2_sub: 'ಹಂತ 5–6: ಲೈವ್ ಕ್ಯಾಮೆರಾ, C2PA & pHash',
    step3_title: '3. ಪರಿಶೀಲನೆ ಮತ್ತು ವರದಿ ರಚನೆ',
    step3_sub: 'ಹಂತ 7–9: 9-ವಿಭಾಗದ ವರದಿ ಮತ್ತು ಇನ್ಶೂರೆನ್ಸ್ ಸಲ್ಲಿಕೆ',
    step1_heading: 'ಹಂತ 1: ಬಹುಭಾಷಾ ಧ್ವನಿ ಮತ್ತು ಪಠ್ಯ ಕ್ಲೈಮ್ ಸಂಭಾಷಣೆ',
    step1_desc:
      'ಕನ್ನಡ, ತೆಲುಗು, ಹಿಂದಿ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಮಾತನಾಡಿ — ವಿಮಾ ಕಂಪನಿಗಾಗಿ ಎಲ್ಲಾ ವಿವರಗಳನ್ನು AI ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಭರ್ತಿ ಮಾಡುತ್ತದೆ.',
    speak_claim_btn: 'ನಿಮ್ಮ ಕ್ಲೈಮ್ ಮಾತನಾಡಿ (ಮೈಕ್ ಒತ್ತಿ)',
    upload_audio_btn: 'ಆಡಿಯೋ ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',
    type_placeholder: 'ಅಥವಾ ಅಪಘಾತದ ವಿವರಗಳನ್ನು ಕನ್ನಡ, ತೆಲುಗು, ಹಿಂದಿ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ...',
    extract_btn: 'ವಿವರ ಪಡೆಯಿರಿ',
    speak_answer_btn: '🎙️ ಉತ್ತರ ಮಾತನಾಡಿ',
    done_speaking_btn: 'ಮಾತು ಮುಗಿದಿದೆ',
    cancel_btn: 'ರದ್ದುಮಾಡಿ',
    reset_btn: 'ಮರುಹೊಂದಿಸಿ',
    next_evidence_btn: 'ಮುಂದೆ: ಸಾಕ್ಷ್ಯಾಧಾರ ಪರಿಶೀಲನೆ',
    continue_step2_btn: 'ಹಂತ 2 ಕ್ಕೆ ಮುಂದುವರಿಯಿರಿ: ಸಾಕ್ಷ್ಯಾಧಾರ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',
    extracted_fields_title: 'ಗುರುತಿಸಲಾದ ಕ್ಲೈಮ್ ವಿವರಗಳು (ವಿಮಾ ಕಂಪನಿಗಾಗಿ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ)',
    extracted_fields_sub: 'ಯಾವುದೇ ಭಾಷೆಯಲ್ಲಿ ಮಾತನಾಡಿದರೂ ವಿಮಾ ಕಂಪನಿಗಾಗಿ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ದಾಖಲಾಗುತ್ತದೆ',
    captured_badge: 'ದಾಖಲಾಗಿದೆ',
    field_policy_reference: 'ಪಾಲಿಸಿ / ವಾಹನ ಸಂಖ್ಯೆ (Policy / Vehicle No)',
    field_vehicle_type: 'ವಾಹನದ ಪ್ರಕಾರ (Vehicle Type)',
    field_incident_location: 'ಅಪಘಾತದ ಸ್ಥಳ (Incident Location)',
    field_incident_date: 'ಅಪಘಾತದ ದಿನಾಂಕ ಮತ್ತು ಸಮಯ (Incident Date)',
    field_damage_description: 'ವಾಹನದ ಹಾನಿಯ ವಿವರ (Damage Description)',
    all_captured_banner:
      'ಎಲ್ಲಾ 5 ಕ್ಲೈಮ್ ವಿವರಗಳು ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ದಾಖಲಾಗಿವೆ! ಈಗ ಹಂತ 2 ಕ್ಕೆ ಮುಂದುವರಿಯಿರಿ.',
    answering_followup: 'ಪ್ರಶ್ನೆಗೆ ಉತ್ತರಿಸಿ',
    vault_title: 'ಗ್ರಾಹಕರ ಕ್ಲೈಮ್ ವಾಲ್ಟ್ ಮತ್ತು ವರದಿ ಕೇಂದ್ರ',
    vault_subtitle:
      'ನಿಮ್ಮ ವಾಹನ ವಿಮಾ ಕ್ಲೈಮ್‌ಗಳು, ಸಾಕ್ಷ್ಯಾಧಾರಗಳ ಪರಿಶೀಲನೆ ಮತ್ತು 9-ವಿಭಾಗದ ಅಧಿಕೃತ ವರದಿಗಳನ್ನು ಇಲ್ಲಿ ನಿರ್ವಹಿಸಿ.',
    start_new_claim: 'ಹೊಸ ಕ್ಲೈಮ್ ಪ್ರಾರಂಭಿಸಿ',
    report_lang_label: 'ವರದಿ ಭಾಷೆ (Report Language):',
    download_preferred_lang_btn: 'ನಿಮ್ಮ ಭಾಷೆಯಲ್ಲಿ ವರದಿ ಡೌನ್‌ಲೋಡ್ / ಪ್ರಿಂಟ್ ಮಾಡಿ',
    download_english_pdf_btn: 'ಅಧಿಕೃತ ಇಂಗ್ಲಿಷ್ PDF (ವಿಮಾ ಕಂಪನಿಗೆ)',
    download_json_btn: 'Canonical JSON ಡೌನ್‌ಲೋಡ್',
    submit_insurer_btn: 'ವಿಮಾ ಕಂಪನಿಗೆ ಸಲ್ಲಿಸಿ',
    settings_title: 'ಸೆಟ್ಟಿಂಗ್ಸ್, ಪ್ರೊಫೈಲ್ ಮತ್ತು ಆಪ್ ಭಾಷೆ',
    settings_tab_lang: 'ಆಪ್ ಭಾಷೆ ಮತ್ತು ಧ್ವನಿ ಸೆಟ್ಟಿಂಗ್ಸ್',
    settings_tab_profile: 'ಗ್ರಾಹಕರ ಪ್ರೊಫೈಲ್ ಮತ್ತು ಪಾಲಿಸಿ',
    choose_app_lang: 'ಆಪ್ ಪಠ್ಯ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ (App Display Language)',
    choose_app_lang_desc:
      'ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿರುವ ಎಲ್ಲಾ ಬಟನ್‌ಗಳು ಮತ್ತು ಸೂಚನೆಗಳನ್ನು ಕನ್ನಡ, ತೆಲುಗು, ಹಿಂದಿ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ಗೆ ಬದಲಾಯಿಸುತ್ತದೆ. ವಿಮಾ ಕಂಪನಿಗೆ ಕಳುಹಿಸುವ ಫಾರ್ಮ್ ವಿವರಗಳು ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿಯೇ ಇರುತ್ತವೆ.',
    choose_report_lang: 'ವರದಿ ಡೌನ್‌ಲೋಡ್ ಭಾಷೆ (Preferred Report Language)',
    choose_voice_mode: 'ಧ್ವನಿ ಗುರುತಿಸುವಿಕೆ ಭಾಷೆ (Voice Recognition Mode)',
    save_settings_btn: 'ಸೆಟ್ಟಿಂಗ್ಸ್ ಉಳಿಸಿ',
    close_btn: 'ಮುಚ್ಚಿ',
    login_badge: 'IRDAI-ಅನುಮೋದಿತ ವಾಹನ ವಿಮಾ ವೇದಿಕೆ',
    login_title: 'ಕ್ಲೈಮ್‌ಸಾಥಿ AI',
    login_subtitle: 'ಸುರಕ್ಷಿತ ಗ್ರಾಹಕರ ಕ್ಲೈಮ್ ವಾಲ್ಟ್ ಮತ್ತು ಸಂಭಾಷಣೆ',
    login_tab_signin: 'ವಾಲ್ಟ್‌ಗೆ ಪ್ರವೇಶಿಸಿ (Sign In)',
    login_tab_register: 'ಹೊಸ ಖಾತೆ ತೆರೆಯಿರಿ',
    login_id_label: 'ಇಮೇಲ್, ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ಅಥವಾ ಗ್ರಾಹಕರ ಐಡಿ',
    login_id_placeholder: 'ಉದಾ: rahul.sharma@claimsathi.in ಅಥವಾ USR-100001',
    login_pwd_label: 'ಪಾಸ್‌ವರ್ಡ್ (Password)',
    login_pwd_placeholder: 'ನಿಮ್ಮ ಪಾಸ್‌ವರ್ಡ್ ನಮೂದಿಸಿ',
    login_otp_toggle_to_otp: 'OTP ಮೂಲಕ ಸೈನ್ ಇನ್ ಮಾಡಿ',
    login_otp_toggle_to_pwd: 'ಪಾಸ್‌ವರ್ಡ್ ಮೂಲಕ ಸೈನ್ ಇನ್ ಮಾಡಿ',
    login_otp_label: '6-ಅಂಕಿಯ ಪರಿಶೀಲನಾ OTP',
    login_otp_placeholder: '6-ಅಂಕಿಯ OTP ನಮೂದಿಸಿ',
    login_otp_send_btn: 'OTP ಕಳುಹಿಸಿ',
    login_submit_btn: 'ಕ್ಲೈಮ್ ವಾಲ್ಟ್‌ಗೆ ಸೈನ್ ಇನ್ ಮಾಡಿ',
    login_quick_demo_title: 'ಡೆಮೊ ಪರೀಕ್ಷಾ ಖಾತೆಗಳು (ಆಯ್ಕೆ ಮಾಡಲು ಕ್ಲಿಕ್ ಮಾಡಿ):',
    claim_detail_back: 'ಕ್ಲೈಮ್ಸ್ ವಾಲ್ಟ್‌ಗೆ ಹಿಂತಿರುಗಿ',
    claim_detail_dossier_title: 'ಅಧಿಕೃತ ವಾಹನ ವಿಮಾ ಕ್ಲೈಮ್ ಡಾಸಿಯರ್',
    claim_detail_dossier_subtitle: 'ಗ್ರಿಪ್ಟೋಗ್ರಾಫಿಕ್ ಆಗಿ ಪರಿಶೀಲಿಸಲಾದ 9-ವಿಭಾಗಗಳ ಕ್ಲೈಮ್ ವರದಿ',
    claim_detail_tab_summary: 'ಡಾಸಿಯರ್ ಸಾರಾಂಶ',
    claim_detail_tab_evidence: 'ಸಾಕ್ಷ್ಯಾಧಾರ & ಪರಿಶೀಲನಾ ಎಂಜಿನ್',
    claim_detail_tab_audit: 'ಆಡಿಟ್ ಮತ್ತು ಟ್ರಯಲ್ ವಿವರ',
    claim_detail_tab_raw: 'ಲೇಯರ್-1 JSON ಡೇಟಾ',
  },
  te: {
    nav_vault: 'కస్టమర్ క్లెయిమ్స్ వాల్ట్',
    nav_new_claim: 'కొత్త క్లెయిమ్ నమోదు',
    nav_settings: 'సెట్టింగ్స్ & ప్రొఫైల్',
    nav_sign_out: 'సైన్ అవుట్',
    app_lang_label: 'యాప్ భాష',
    step1_title: '1. బహుభాషా AI వివరాలు సేకరణ',
    step1_sub: 'దశలు 2–4: వాయిస్ / టెక్స్ట్ సంభాషణ',
    step2_title: '2. సాక్ష్యాలు & ఇంటిగ్రిటీ తనిఖీ',
    step2_sub: 'దశలు 5–6: లైవ్ కెమెరా, C2PA & pHash',
    step3_title: '3. సమీక్ష & రిపోర్ట్ తయారీ',
    step3_sub: 'దశలు 7–9: 9-విభాగాల రిపోర్ట్ & సబ్మిషన్',
    step1_heading: 'స్టెప్ 1: బహుభాషా వాయిస్ & టెక్స్ట్ క్లెయిమ్ సంభాషణ',
    step1_desc:
      'తెలుగు, కన్నడ, హిందీ లేదా ఇంగ్లీష్‌లో మాట్లాడండి — ఇన్సూరెన్స్ కంపెనీ కోసం అన్ని వివరాలను AI ఆటోమేటిక్‌గా ఇంగ్లీష్‌లో నింపుతుంది.',
    speak_claim_btn: 'మీ క్లెయిమ్ మాట్లాడండి (మైక్ నొక్కండి)',
    upload_audio_btn: 'ఆడియో ఫైల్ అప్లోడ్ చేయండి',
    type_placeholder: 'లేదా యాక్సిడెంట్ వివరాలను తెలుగు, కన్నడ, హిందీ లేదా ఇంగ్లీష్‌లో టైప్ చేయండి...',
    extract_btn: 'వివరాలు పొందండి',
    speak_answer_btn: '🎙️ సమాధానం మాట్లాడండి',
    done_speaking_btn: 'మాట్లాడటం పూర్తయింది',
    cancel_btn: 'రద్దు చేయండి',
    reset_btn: 'రీసెట్',
    next_evidence_btn: 'తదుపరి: సాక్ష్యాల పరిశీలన',
    continue_step2_btn: 'స్టెప్ 2 కి వెళ్ళండి: సాక్ష్యాలు అప్లోడ్ చేయండి',
    extracted_fields_title: 'గుర్తించిన క్లెయిమ్ వివరాలు (ఇన్సూరెన్స్ కోసం ఇంగ్లీష్‌లో)',
    extracted_fields_sub: 'ఏ భాషలో మాట్లాడినా ఇన్సూరెన్స్ కంపెనీ కోసం ఇంగ్లీష్‌లో నమోదు చేయబడుతుంది',
    captured_badge: 'నమోదైంది',
    field_policy_reference: 'పాలసీ / వాహన నంబర్ (Policy / Vehicle No)',
    field_vehicle_type: 'వాహనం రకం (Vehicle Type)',
    field_incident_location: 'ప్రమాద ప్రదేశం (Incident Location)',
    field_incident_date: 'ప్రమాద తేదీ & సమయం (Incident Date)',
    field_damage_description: 'వాహన డ్యామేజ్ వివరాలు (Damage Description)',
    all_captured_banner:
      'అన్ని 5 క్లెయిమ్ వివరాలు ఇంగ్లీష్‌లో నమోదయ్యాయి! ఇప్పుడు స్టెప్ 2 కి వెళ్ళండి.',
    answering_followup: 'తదుపరి ప్రశ్నకు సమాధానం',
    vault_title: 'కస్టమర్ క్లెయిమ్స్ వాల్ట్ & రిపోర్ట్ సెంటర్',
    vault_subtitle:
      'మీ వాహన ఇన్సూరెన్స్ క్లెయిమ్స్, సాక్ష్యాల తనిఖీ మరియు 9-విభాగాల అధికారిక రిపోర్ట్‌లను ఇక్కడ నిర్వహించండి.',
    start_new_claim: 'కొత్త క్లెయిమ్ ప్రారంభించండి',
    report_lang_label: 'రిపోర్ట్ భాష (Report Language):',
    download_preferred_lang_btn: 'మీ భాషలో రిపోర్ట్ డౌన్‌లోడ్ / ప్రింట్ చేయండి',
    download_english_pdf_btn: 'అధికారిక ఇంగ్లీష్ PDF (ఇన్సూరెన్స్ కంపెనీకి)',
    download_json_btn: 'Canonical JSON డౌన్‌లోడ్',
    submit_insurer_btn: 'ఇన్సూరెన్స్ కంపెనీకి పంపండి',
    settings_title: 'సెట్టింగ్స్, ప్రొఫైల్ & యాప్ భాష',
    settings_tab_lang: 'యాప్ భాష & వాయిస్ సెట్టింగ్స్',
    settings_tab_profile: 'కస్టమర్ ప్రొఫైల్ & పాలసీ',
    choose_app_lang: 'యాప్ టెక్స్ట్ భాషను ఎంచుకోండి (App Display Language)',
    choose_app_lang_desc:
      'వెబ్‌సైట్‌లోని అన్ని బటన్లు మరియు సూచనలను తెలుగు, కన్నడ, హిందీ లేదా ఇంగ్లీష్‌లోకి మారుస్తుంది. ఇన్సూరెన్స్ కంపెనీకి పంపే ఫారమ్ వివరాలు ఇంగ్లీష్‌లోనే ఉంటాయి.',
    choose_report_lang: 'రిపోర్ట్ డౌన్‌లోడ్ భాష (Preferred Report Language)',
    choose_voice_mode: 'వాయిస్ గుర్తింపు భాష (Voice Recognition Mode)',
    save_settings_btn: 'సెట్టింగ్స్ సేవ్ చేయండి',
    close_btn: 'మూసివేయండి',
    login_badge: 'IRDAI-సమ్మతి మోటార్ ఇన్సూరెన్స్ ప్లాట్‌ఫారమ్',
    login_title: 'క్లెయిమ్‌సాథి AI',
    login_subtitle: 'సురక్షిత కస్టమర్ క్లెయిమ్స్ వాల్ట్ & వాయిస్ ఇన్టేక్',
    login_tab_signin: 'వాల్ట్‌లోకి ప్రవేశించండి (Sign In)',
    login_tab_register: 'కొత్త ఖాతా తెరవండి',
    login_id_label: 'ఈమెయిల్, మొబైల్ లేదా కస్టమర్ ID',
    login_id_placeholder: 'ఉదా: rahul.sharma@claimsathi.in లేదా USR-100001',
    login_pwd_label: 'పాస్‌వర్డ్ (Password)',
    login_pwd_placeholder: 'మీ పాస్‌వర్డ్ నమోదు చేయండి',
    login_otp_toggle_to_otp: 'OTP ద్వారా సైన్ ఇన్ చేయండి',
    login_otp_toggle_to_pwd: 'పాస్‌వర్డ్ ద్వారా సైన్ ఇన్ చేయండి',
    login_otp_label: '6-అంకెల వెరిఫికేషన్ OTP',
    login_otp_placeholder: '6-అంకెల OTP నమోదు చేయండి',
    login_otp_send_btn: 'OTP పంపండి',
    login_submit_btn: 'క్లెయిమ్స్ వాల్ట్‌లోకి ప్రవేశించండి',
    login_quick_demo_title: 'డెమో ఖాతాలు (ఆటో-ఫిల్ చేయడానికి క్లిక్ చేయండి):',
    claim_detail_back: 'క్లెయిమ్స్ వాల్ట్‌కి తిరిగి వెళ్ళండి',
    claim_detail_dossier_title: 'అధికారిక మోటార్ ఇన్సూరెన్స్ క్లెయిమ్ డోసియర్',
    claim_detail_dossier_subtitle: 'క్రిప్టోగ్రాఫికల్లీ వెరిఫైడ్ 9-సెక్షన్ల క్లెయిమ్ రిపోర్ట్',
    claim_detail_tab_summary: 'డోసియర్ సారాంశం',
    claim_detail_tab_evidence: 'సాక్ష్యాలు & ఇంటిగ్రిటీ ఇంజిన్',
    claim_detail_tab_audit: 'ఆడిట్ & ప్రూవెనెన్స్ వివరాలు',
    claim_detail_tab_raw: 'లేయర్-1 JSON డేటా',
  },
  hi: {
    nav_vault: 'ग्राहक क्लेम वॉल्ट',
    nav_new_claim: 'नया क्लेम दर्ज करें',
    nav_settings: 'सेटिंग्स और प्रोफ़ाइल',
    nav_sign_out: 'साइन आउट',
    app_lang_label: 'ऐप की भाषा',
    step1_title: '1. बहुभाषी AI क्लेम इनटेक',
    step1_sub: 'चरण 2–4: आवाज़ / टेक्स्ट संवाद',
    step2_title: '2. साक्ष्य और सत्यता जांच',
    step2_sub: 'चरण 5–6: लाइव कैमरा, C2PA और pHash',
    step3_title: '3. समीक्षा और रिपोर्ट तैयार करें',
    step3_sub: 'चरण 7–9: 9-अनुभाग रिपोर्ट और सबमिशन',
    step1_heading: 'चरण 1: बहुभाषी आवाज़ और टेक्स्ट क्लेम संवाद',
    step1_desc:
      'हिन्दी, कन्नड़, तेलुगु या अंग्रेजी में बोलें — बीमा कंपनी के लिए सभी फ़ील्ड अपने आप अंग्रेजी में भरे जाते हैं।',
    speak_claim_btn: 'अपना क्लेम बोलें (माइक दबाएं)',
    upload_audio_btn: 'ऑडियो फ़ाइल अपलोड करें',
    type_placeholder: 'या दुर्घटना का विवरण हिन्दी, कन्नड़, तेलुगु या अंग्रेजी में टाइप करें...',
    extract_btn: 'विवरण निकालें',
    speak_answer_btn: '🎙️ उत्तर बोलें',
    done_speaking_btn: 'बोलना पूरा हुआ',
    cancel_btn: 'रद्द करें',
    reset_btn: 'रीसेट',
    next_evidence_btn: 'आगे: साक्ष्य जांच',
    continue_step2_btn: 'चरण 2 पर जाएं: साक्ष्य अपलोड और जांच करें',
    extracted_fields_title: 'निकाले गए क्लेम विवरण (बीमा कंपनी हेतु अंग्रेजी में)',
    extracted_fields_sub: 'किसी भी भारतीय भाषा में बोलें → बीमा कंपनी के लिए अंग्रेजी में दर्ज',
    captured_badge: 'दर्ज',
    field_policy_reference: 'पॉलिसी / गाड़ी नंबर (Policy / Vehicle No)',
    field_vehicle_type: 'वाहन का प्रकार (Vehicle Type)',
    field_incident_location: 'हादसे का स्थान (Incident Location)',
    field_incident_date: 'हादसे की तारीख और समय (Incident Date)',
    field_damage_description: 'नुकसान का विवरण (Damage Description)',
    all_captured_banner: 'सभी 5 मुख्य विवरण अंग्रेजी में दर्ज हो गए हैं! अब चरण 2 पर आगे बढ़ें।',
    answering_followup: 'अगले प्रश्न का उत्तर',
    vault_title: 'ग्राहक क्लेम वॉल्ट और रिपोर्ट केंद्र',
    vault_subtitle: 'अपने वाहन बीमा क्लेम, साक्ष्य जांच और 9-अनुभाग रिपोर्ट प्रबंधित करें।',
    start_new_claim: 'नया क्लेम शुरू करें',
    report_lang_label: 'रिपोर्ट की भाषा (Report Language):',
    download_preferred_lang_btn: 'अपनी भाषा में रिपोर्ट डाउनलोड / प्रिंट करें',
    download_english_pdf_btn: 'आधिकारिक अंग्रेजी PDF (बीमा कंपनी हेतु)',
    download_json_btn: 'Canonical JSON डाउनलोड',
    submit_insurer_btn: 'बीमा कंपनी को भेजें',
    settings_title: 'सेटिंग्स, प्रोफ़ाइल और ऐप भाषा',
    settings_tab_lang: 'ऐप भाषा और आवाज़ सेटिंग्स',
    settings_tab_profile: 'ग्राहक प्रोफ़ाइल और पॉलिसी',
    choose_app_lang: 'ऐप की भाषा चुनें (App Display Language)',
    choose_app_lang_desc:
      'वेबसाइट के सभी बटन और निर्देश आपकी चुनी हुई भाषा (हिन्दी, कन्नड़, तेलुगु या अंग्रेजी) में बदल जाएंगे। बीमा कंपनी को भेजे जाने वाले फ़ील्ड अंग्रेजी में ही रहेंगे।',
    choose_report_lang: 'रिपोर्ट डाउनलोड भाषा (Preferred Report Language)',
    choose_voice_mode: 'आवाज़ पहचान मोड (Voice Recognition Mode)',
    save_settings_btn: 'सेटिंग्स सहेजें',
    close_btn: 'बंद करें',
    login_badge: 'IRDAI-अनुपालन मोटर बीमा प्लेटफॉर्म',
    login_title: 'क्लेमसाथी AI',
    login_subtitle: 'सुरक्षित ग्राहक क्लेम वॉल्ट और वॉयस इनटेक',
    login_tab_signin: 'वॉल्ट में प्रवेश करें (Sign In)',
    login_tab_register: 'नया खाता बनाएं',
    login_id_label: 'ईमेल, फोन नंबर या ग्राहक आईडी',
    login_id_placeholder: 'उदा: rahul.sharma@claimsathi.in या USR-100001',
    login_pwd_label: 'पासवर्ड (Password)',
    login_pwd_placeholder: 'अपना पासवर्ड दर्ज करें',
    login_otp_toggle_to_otp: 'OTP के माध्यम से साइन इन करें',
    login_otp_toggle_to_pwd: 'पासवर्ड के माध्यम से साइन इन करें',
    login_otp_label: '6-अंकीय सत्यापन OTP',
    login_otp_placeholder: '6-अंकीय OTP दर्ज करें',
    login_otp_send_btn: 'OTP भेजें',
    login_submit_btn: 'ग्राहक क्लेम वॉल्ट में साइन इन करें',
    login_quick_demo_title: 'डेमो परीक्षण खाते (स्वतः भरने हेतु क्लिक करें):',
    claim_detail_back: 'क्लेम्स वॉल्ट पर वापस जाएं',
    claim_detail_dossier_title: 'आधिकारिक मोटर बीमा क्लेम डोज़ियर',
    claim_detail_dossier_subtitle: 'क्रिप्टोग्राफ़िक रूप से सत्यापित 9-अनुभाग रिपोर्ट',
    claim_detail_tab_summary: 'डोज़ियर सारांश',
    claim_detail_tab_evidence: 'साक्ष्य और सत्यता इंजन',
    claim_detail_tab_audit: 'ऑडिट और प्रूवेनेंस विवरण',
    claim_detail_tab_raw: 'लेयर-1 JSON डेटा',
  },
  ta: {
    nav_vault: 'வாடிக்கையாளர் கோரிக்கைகள்',
    nav_new_claim: 'புதிய கோரிக்கை',
    nav_settings: 'அமைப்புகள் & சுயவிவரம்',
    nav_sign_out: 'வெளியேறு',
    app_lang_label: 'செயலி மொழி',
    step1_title: '1. பன்மொழி AI தகவல் சேகரிப்பு',
    step1_sub: 'படி 2–4: குரல் / உரை உரையாடல்',
    step2_title: '2. ஆதாரம் & சரிபார்ப்பு',
    step2_sub: 'படி 5–6: நேரடி கேமரா, C2PA & pHash',
    step3_title: '3. ஆய்வு & அறிக்கை உருவாக்கம்',
    step3_sub: 'படி 7–9: 9-பிரிவு அறிக்கை',
    step1_heading: 'படி 1: பன்மொழி குரல் மற்றும் உரை கோரிக்கை',
    step1_desc:
      'தமிழ், கன்னடம், தெலுங்கு, இந்தி அல்லது ஆங்கிலத்தில் பேசுங்கள் — காப்பீட்டு நிறுவனத்திற்காக அனைத்து விவரங்களும் ஆங்கிலத்தில் நிரப்பப்படும்.',
    speak_claim_btn: 'உங்கள் கோரிக்கையைப் பேசுங்கள்',
    upload_audio_btn: 'ஆடியோ பதிவேற்றம்',
    type_placeholder: 'அல்லது விபத்து விவரங்களைத் தட்டச்சு செய்யவும்...',
    extract_btn: 'விவரம் பெறு',
    speak_answer_btn: '🎙️ பதிலைப் பேசுங்கள்',
    done_speaking_btn: 'பேசி முடிந்தது',
    cancel_btn: 'ரத்துசெய்',
    reset_btn: 'மீட்டமை',
    next_evidence_btn: 'அடுத்து: ஆதார சரிபார்ப்பு',
    continue_step2_btn: 'படி 2 க்குச் செல்லவும்: ஆதாரங்களைப் பதிவேற்றவும்',
    extracted_fields_title: 'கோரிக்கை விவரங்கள் (காப்பீட்டு நிறுவனத்திற்காக ஆங்கிலத்தில்)',
    extracted_fields_sub: 'எந்த மொழியில் பேசினாலும் ஆங்கிலத்தில் பதிவு செய்யப்படும்',
    captured_badge: 'பதிவானது',
    field_policy_reference: 'பாலிசி / வாகன எண் (Policy / Vehicle No)',
    field_vehicle_type: 'வாகன வகை (Vehicle Type)',
    field_incident_location: 'விபத்து நடந்த இடம் (Incident Location)',
    field_incident_date: 'விபத்து தேதி & நேரம் (Incident Date)',
    field_damage_description: 'சேத விவரம் (Damage Description)',
    all_captured_banner: 'அனைத்து 5 விவரங்களும் ஆங்கிலத்தில் பதிவாகியுள்ளன! படி 2 க்குச் செல்லவும்.',
    answering_followup: 'பதில் அளிக்கவும்',
    vault_title: 'வாடிக்கையாளர் கோரிக்கை மையம்',
    vault_subtitle: 'உங்கள் வாகன காப்பீட்டு கோரிக்கைகள் மற்றும் அறிக்கைகளை நிர்வகிக்கவும்.',
    start_new_claim: 'புதிய கோரிக்கையைத் தொடங்கு',
    report_lang_label: 'அறிக்கை மொழி (Report Language):',
    download_preferred_lang_btn: 'உங்கள் மொழியில் அறிக்கை பதிவிறக்கம் / அச்சிடு',
    download_english_pdf_btn: 'அதிகாரப்பூர்வ ஆங்கில PDF',
    download_json_btn: 'Canonical JSON',
    submit_insurer_btn: 'காப்பீட்டு நிறுவனத்திற்கு அனுப்பு',
    settings_title: 'அமைப்புகள், சுயவிவரம் & மொழி',
    settings_tab_lang: 'செயலி மொழி & குரல்',
    settings_tab_profile: 'வாடிக்கையாளர் சுயவிவரம்',
    choose_app_lang: 'செயலி மொழியைத் தேர்ந்தெடுக்கவும்',
    choose_app_lang_desc:
      'இணையதளத்தின் அனைத்து பொத்தான்களும் உங்கள் மொழியில் மாறும். காப்பீட்டு நிறுவனத்திற்கு அனுப்பப்படும் விவரங்கள் ஆங்கிலத்தில் இருக்கும்.',
    choose_report_lang: 'அறிக்கை பதிவிறக்க மொழி',
    choose_voice_mode: 'குரல் அறிதல் மொழி',
    save_settings_btn: 'சேமி',
    close_btn: 'மூடு',
    login_badge: 'IRDAI-ஒழுங்குமுறை வாகன காப்பீட்டு தளம்',
    login_title: 'கிளைம்சாதி AI',
    login_subtitle: 'பாதுகாப்பான வாடிக்கையாளர் கிளைம் வால்ட் & குரல் பதிவு',
    login_tab_signin: 'வால்ட்டில் உள்நுழையவும் (Sign In)',
    login_tab_register: 'புதிய கணக்கு தொடங்கவும்',
    login_id_label: 'மின்னஞ்சல், மொபைல் அல்லது வாடிக்கையாளர் ID',
    login_id_placeholder: 'எ.கா: rahul.sharma@claimsathi.in அல்லது USR-100001',
    login_pwd_label: 'கடவுச்சொல் (Password)',
    login_pwd_placeholder: 'கடவுச்சொல்லை உள்ளிடவும்',
    login_otp_toggle_to_otp: 'OTP மூலம் உள்நுழைக',
    login_otp_toggle_to_pwd: 'கடவுச்சொல் மூலம் உள்நுழைக',
    login_otp_label: '6-இலக்க சரிபார்ப்பு OTP',
    login_otp_placeholder: '6-இலக்க OTP உள்ளிடவும்',
    login_otp_send_btn: 'OTP அனுப்பு',
    login_submit_btn: 'கிளைம் வால்ட்டில் உள்நுழையவும்',
    login_quick_demo_title: 'டெமோ சோதனைக் கணக்குகள் (தானாக நிரப்ப கிளிக் செய்க):',
    claim_detail_back: 'கிளைம்ஸ் வால்ட்டிற்குத் திரும்பு',
    claim_detail_dossier_title: 'அதிகாரப்பூர்வ வாகன காப்பீட்டு கோரிக்கை ஆவணம்',
    claim_detail_dossier_subtitle: 'கிரிப்டோகிராஃபிக் முறையில் சரிபார்க்கப்பட்ட 9-பிரிவு அறிக்கை',
    claim_detail_tab_summary: 'கோரிக்கை சுருக்கம்',
    claim_detail_tab_evidence: 'ஆதாரம் & ஒருமைப்பாடு எஞ்சின்',
    claim_detail_tab_audit: 'தணிக்கை & ஆதாரத் தடம்',
    claim_detail_tab_raw: 'அடுக்கு-1 JSON தரவு',
  },
}

interface AppSettingsContextValue {
  appLanguage: AppLanguageCode
  setAppLanguage: (lang: AppLanguageCode) => void
  preferredReportLanguage: AppLanguageCode
  setPreferredReportLanguage: (lang: AppLanguageCode) => void
  defaultVoiceLanguage: string
  setDefaultVoiceLanguage: (lang: string) => void
  isSettingsOpen: boolean
  setIsSettingsOpen: (open: boolean) => void
  t: (key: string) => string
}

const AppSettingsContext = createContext<AppSettingsContextValue | null>(null)

export function AppSettingsProvider({ children }: { children: React.ReactNode }) {
  const [appLanguage, setAppLanguageState] = useState<AppLanguageCode>(() => {
    const saved = localStorage.getItem('claimsathi_app_lang') as AppLanguageCode | null
    return saved && ['en', 'kn', 'te', 'hi', 'ta'].includes(saved) ? saved : 'en'
  })

  const [preferredReportLanguage, setPreferredReportLanguageState] = useState<AppLanguageCode>(() => {
    const saved = localStorage.getItem('claimsathi_report_lang') as AppLanguageCode | null
    return saved && ['en', 'kn', 'te', 'hi', 'ta'].includes(saved) ? saved : 'en'
  })

  const [defaultVoiceLanguage, setDefaultVoiceLanguageState] = useState<string>(() => {
    return localStorage.getItem('claimsathi_voice_lang') || 'indic-auto'
  })

  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  const setAppLanguage = (lang: AppLanguageCode) => {
    setAppLanguageState(lang)
    localStorage.setItem('claimsathi_app_lang', lang)
    // Also default report download language to match app language so user can read their report easily
    setPreferredReportLanguageState(lang)
    localStorage.setItem('claimsathi_report_lang', lang)
  }

  const setPreferredReportLanguage = (lang: AppLanguageCode) => {
    setPreferredReportLanguageState(lang)
    localStorage.setItem('claimsathi_report_lang', lang)
  }

  const setDefaultVoiceLanguage = (lang: string) => {
    setDefaultVoiceLanguageState(lang)
    localStorage.setItem('claimsathi_voice_lang', lang)
  }

  useEffect(() => {
    document.documentElement.lang = appLanguage
  }, [appLanguage])

  const t = (key: string): string => {
    return TRANSLATIONS[appLanguage]?.[key] || TRANSLATIONS.en[key] || key
  }

  return (
    <AppSettingsContext.Provider
      value={{
        appLanguage,
        setAppLanguage,
        preferredReportLanguage,
        setPreferredReportLanguage,
        defaultVoiceLanguage,
        setDefaultVoiceLanguage,
        isSettingsOpen,
        setIsSettingsOpen,
        t,
      }}
    >
      {children}
    </AppSettingsContext.Provider>
  )
}

export function useAppSettings() {
  const ctx = useContext(AppSettingsContext)
  if (!ctx) {
    throw new Error('useAppSettings must be used within AppSettingsProvider')
  }
  return ctx
}

