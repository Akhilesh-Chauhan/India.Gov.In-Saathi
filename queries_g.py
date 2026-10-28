# Index-grounded questions built on the developer's seed file (Documents Given/qa-golden-set-seed-top10-sources.md,
# 16-Oct-2026): every answer is in a chunk the bot has indexed, so a miss is a retrieval failure, not missing data.
# Row: (chunk_key, topic, qtype, persona, level, lang, style, focus, priority, query, expected)
# Markers: [IDX] golden taken from the indexed chunk text; [IDX-STALE] the chunk is outdated - the golden follows the
# current official position and the bot must not present the old text as current; plus the usual [V]/[S]/[R].

GROUPS_G = [
("Index-grounded (developer seed)", [
# ---- UIDAI ----
("uidai-gov-in#A", "What Aadhaar is", "DET", "SCH", "L0", "EN", "S", "CITE", "P1",
 "What exactly is an Aadhaar number?",
 "A 12-digit random number assigned to a person after completing enrolment; a digital identity that can be authenticated "
 "through biometrics or mobile OTP. Cites uidai.gov.in 'Your Aadhaar'. [IDX]"),
("uidai-gov-in#A", "UIDAI does not collect caste/religion", "DET", "HOME", "L0", "HI", "W", "CITE", "P1",
 "क्या आधार बनवाते समय मेरा धर्म या जाति पूछी जाती है?",
 "No: UIDAI policy bars it from collecting sensitive information such as religion, caste, community, class, ethnicity, "
 "income and health; data is collected only to issue Aadhaar and confirm identity. [IDX]"),
("uidai-gov-in#B", "Enrolment free + documents", "PROC", "LAB", "L0", "HG", "T", "CITE", "P0",
 "aadhaar banwane me kitna paisa lagta hai aur kaunse document chahiye",
 "Aadhaar enrolment is free; go to any authorised enrolment centre anywhere in India with proof of identity and proof of "
 "address - common ones are voter ID, ration card, passport and driving licence; fill the form, give biometrics, collect the "
 "acknowledgement slip with Enrolment ID. Fail if any enrolment fee is stated. [IDX]"),
("uidai-gov-in#C", "Child enrolled before 5", "PROC", "MOM", "L1", "EN", "S", "CITE", "P1",
 "My son got Aadhaar when he was 4. He has just turned 5. What do we need to do?",
 "The child must update / re-enrol all biometrics on turning 5 (and again at 15). The fee sheet makes the first update "
 "between 5 and 7 free. Cites uidai.gov.in 'Updating data on Aadhaar'. [IDX][V]"),
("uidai-gov-in#C", "Adult biometric update interval", "RULE", "PEN", "L1", "EN", "S", "CITE", "P2",
 "How often should adults update their biometrics in Aadhaar?",
 "UIDAI recommends that Aadhaar holders above 15 update their biometric data every 10 years (a recommendation, not a "
 "mandatory deadline). [IDX]"),
# ---- Income Tax (PAN) ----
("incometax-gov-in#A", "PAN allotment form (Rules 2026)", "RULE", "CA", "L2", "EN", "L", "CITE", "P1",
 "Under the Income-tax Rules 2026, which forms are used to apply for allotment of a PAN?",
 "Rule 158: an application under section 262 is made in Form No. 93, 94, 95 or 96 as the case may be; a common application "
 "form notified by the Central Government may also be used; a person with an Aadhaar number can apply by intimating it. "
 "Cites the notified Income-tax Rules 2026 PDF on incometax.gov.in. [IDX]"),
("incometax-gov-in#A", "New PAN card - plain question", "PROC", "STU", "L0", "HG", "T", "ROUTE", "P0",
 "naya pan card kaise banaye",
 "Coverage probe (developer note: no plain-language 'new PAN' page is indexed). PASS if it answers from the indexed Rule "
 "158 text with citation (forms 93-96 / Aadhaar-based allotment) or admits the gap and links the Income Tax portal; FAIL "
 "if it invents steps, cites unrelated pages (e.g. an NRI booklet) or points to outdated sites. [IDX]"),
("incometax-gov-in#B", "PAN application deadline", "RULE", "CA", "L2", "EN", "L", "CITE", "P2",
 "By when must a person apply for PAN if their total income exceeds the non-taxable limit?",
 "On or before 31 May of the tax year immediately following; a person whose business turnover is likely to exceed "
 "Rs 5,00,000 must apply before the end of that tax year (Income-tax Rules 2026, rule 158 table). [IDX]"),
("incometax-gov-in#C", "Check refund status", "PROC", "PEN", "L1", "EN", "S", "CITE", "P0",
 "How do I check my income tax refund status online?",
 "Log in to the e-Filing portal; if PAN is not linked with Aadhaar a pop-up says PAN is inoperative (Link Now); then e-File > "
 "Income Tax Returns > View Filed Returns and check refund status for the assessment year. Cites the Refund Status user "
 "manual; cannot see the user's refund. [IDX]"),
("incometax-gov-in#D", "Form 10A condonation", "PROC", "CA", "L2", "EN", "L", "CITE", "P2",
 "How do I file a condonation request for a delayed Form 10A on the e-filing portal?",
 "Login > Services > Condonation request > Application for statutory Forms > + Create Condonation request > fill details > "
 "e-verify; note the transaction ID. [IDX]"),
# ---- Indian Railways ----
("indianrailways-gov-in#A", "Refund time after cancellation", "DET", "LAB", "L0", "HG", "T", "CITE", "P0",
 "ticket cancel kiya tha, paisa kitne din me wapas aayega",
 "Per the Railways Citizen Charter the refund is credited within 7 working days to the account from which the ticket was "
 "booked. [IDX]"),
("indianrailways-gov-in#A", "RailMadad channels", "PROC", "WID", "L0", "HI", "E", "CITE", "P1",
 "ट्रेन में सफाई नहीं है, शिकायत कैसे करूं?",
 "RailMadad: helpline 139, SMS 'Madad <complaint>' to 139, railmadad.gov.in, the RailMadad app, social media @RailMinIndia, "
 "e-mail, or the complaint book with ticket-checking staff / station master. [IDX]"),
("indianrailways-gov-in#B", "GST on train fares", "DET", "STU", "L1", "EN", "S", "CITE", "P1",
 "Do I pay GST on a sleeper class train ticket?",
 "No: GST applies only to AC and First class fares; not to sleeper, second class reserved or unreserved. [IDX]"),
("indianrailways-gov-in#C", "PNR status - not in index", "USE", "GRAD", "L0", "EN", "S", "ABST", "P1",
 "How do I check my PNR status?",
 "Coverage probe: the indexed railway content has no PNR self-service (developer note); IRCTC is listed in the bot's "
 "registry but reported as not crawled. PASS if it links an official enquiry channel (e.g. 139 / Indian Railways / IRCTC) "
 "without inventing steps; FAIL if it fabricates a procedure or cites the internal engineering code. [IDX]"),
# ---- PM-KISAN vs PM-KMY ----
("pmkisan-gov-in#A", "PM-KISAN benefit", "DET", "FARM", "L1", "HI", "S", "FRESH", "P0",
 "पीएम किसान में कितना पैसा मिलता है और कितनी किस्तों में?",
 "Rs 6,000 a year per family in three equal instalments (every four months). Must NOT say the scheme is limited to 2 "
 "hectares - the original 2019 guideline in the index says so, but the revised scheme covers all landholding farmer "
 "families subject to exclusions (precedence: revised guidelines, G05). [IDX-STALE][S]"),
("pmkisan-gov-in#A", "Land size limit trap", "RULE", "FARM", "L1", "HG", "W", "FRESH", "P0",
 "mere paas 4 hectare zameen hai, pm kisan sirf 2 hectare walon ke liye hai na?",
 "Corrects the user: the 2-hectare limit was in the original guideline; the revised PM-KISAN covers all landholding farmer "
 "families regardless of holding size, subject to the exclusion criteria (no eligibility verdict). Cites the revised "
 "guidelines, not only the original. [IDX-STALE][S]"),
("pmkisan-gov-in#B", "Aadhaar mandatory?", "RULE", "FARM", "L1", "EN", "S", "FRESH", "P1",
 "Is Aadhaar mandatory for getting PM-KISAN money?",
 "Yes, Aadhaar is mandatory (it was optional only for the 1st instalment); the exemption for Assam, Meghalaya and J&K ended "
 "on 31.03.2020 and must not be presented as current. eKYC is also required (portal). [IDX-STALE]"),
("pmkisan-gov-in#C", "PM-KMY pension amount", "DET", "FARM", "L1", "EN", "S", "CITE", "P0",
 "How much pension does a farmer get under PM Kisan Maan-Dhan Yojana and how much does he have to contribute?",
 "PM-KMY (a separate, contributory pension scheme): Rs 3,000 per month from age 60; the farmer contributes Rs 55 to Rs 200 "
 "per month until 60 and the Centre contributes an equal amount; entry age 18-40; for small and marginal farmers. Must not "
 "mix it with PM-KISAN's Rs 6,000 a year. [IDX]"),
("pmkisan-gov-in#C", "Pension vs income support confusion", "DET", "FARM", "L0", "HG", "W", "CITE", "P0",
 "pm kisan me budhape me pension kitni milti hai",
 "Distinguishes the schemes: PM-KISAN is income support (Rs 6,000 a year, non-contributory), not a pension; the farmer "
 "pension is PM-KMY (Rs 3,000 a month at 60, contributory, join at 18-40). Fail if it says PM-KISAN pays a pension or "
 "gives Rs 3,000 as PM-KISAN's amount. [IDX]"),
("pmkisan-gov-in#D", "No land in own name", "DET", "LAB", "L0", "HI", "S", "CITE", "P1",
 "मेरे नाम पर जमीन नहीं है, पिता के नाम पर है, क्या मुझे पीएम किसान मिलेगा?",
 "Landholding in one's own name per State land records is the criterion; without it the person is not covered (published "
 "criteria, no personal verdict; the Department decides). Check the citation is the right scheme's document - the developer "
 "notes this text sits in the PM-KMY FAQ. [IDX]"),
# ---- EPFO ----
("epfo-gov-in#A", "EPF contribution split", "DET", "GRAD", "L1", "EN", "S", "CITE", "P1",
 "How much do I and my employer contribute to EPF?",
 "Both contribute 12% of basic wages + dearness allowance; the employee's share goes fully to EPF; the employer's share is "
 "split between EPF, EPS and EDLI. [IDX]"),
("epfo-gov-in#A", "Full withdrawal when unemployed", "RULE", "LAB", "L0", "HG", "S", "FRESH", "P0",
 "naukri chhute 2 mahine ho gaye, kya poora PF nikal sakta hu?",
 "The indexed EPFO page (last updated 12-11-2025) says full withdrawal after 2 months of unemployment; the EPF Scheme 2026 "
 "(Gazette 29-06-2026) replaced the 1952 scheme - the answer must follow the current scheme text with its date or flag the "
 "conflict (G05). Reviewer: confirm the 2026 final-settlement rule. [IDX-STALE][R]"),
("epfo-gov-in#B", "UAN basics", "DET", "STU", "L0", "EN", "S", "CITE", "P1",
 "What is a UAN and can I generate it myself?",
 "UAN is a 12-digit number linked to the member's active PF account; an individual can generate it using Aadhaar (currently "
 "via face authentication on UMANG). [IDX][V]"),
("epfo-gov-in#B", "EPS scheme certificate", "DET", "PEN", "L1", "EN", "S", "CITE", "P2",
 "Who gets an EPS scheme certificate?",
 "A member with 10 or more years of service who has not reached 58 is mandatorily issued a scheme certificate. [IDX]"),
("epfo-gov-in#C", "Claim not settled in 20 days", "PROC", "LAB", "L1", "HI", "E", "CITE", "P0",
 "पीएफ क्लेम 20 दिन से ज्यादा हो गए, पैसा नहीं आया, शिकायत किससे करूं?",
 "Approach the Regional PF Commissioner (grievances); file a complaint on EPFiGMS (epfigms.gov.in, 'For Employees'); or "
 "attend 'Nidhi Aapke Nikat' held on the 10th of every month. [IDX]"),
("epfo-gov-in#D", "PM-VBRY registration", "RULE", "FOUN", "L2", "EN", "L", "CITE", "P2",
 "My company is already registered with EPFO. Do we need to register again for PM Viksit Bharat Rozgar Yojana?",
 "No fresh registration; the establishment must furnish its PAN, GSTN and the PAN-linked bank account of the employer. "
 "Must not confuse PM-VBRY with the EPF scheme itself. [IDX]"),
# ---- NFSA ----
("nfsa-gov-in#A", "Head of household on ration card", "DET", "HOME", "L0", "HI", "S", "CITE", "P1",
 "राशन कार्ड में परिवार का मुखिया कौन होता है?",
 "Under NFSA the eldest woman of the household aged 18 or above is the head of household for issuing ration cards. [IDX]"),
("nfsa-gov-in#A", "NFSA coverage", "DET", "JOUR", "L2", "EN", "D", "CITE", "P2",
 "How many people are covered under the National Food Security Act right now?",
 "About 80 crore persons covered out of a maximum coverage of 81.34 crore (nfsa.gov.in NFSA Act page), with its date. [IDX]"),
("nfsa-gov-in#B", "Grain entitlement and price", "DET", "WID", "L0", "HI", "S", "FRESH", "P0",
 "राशन में हर व्यक्ति को कितना अनाज मिलता है और कितने रुपये किलो?",
 "5 kg per person per month for priority households (AAY: 35 kg per household); it is FREE under PMGKAY from 1 Jan 2024 "
 "for five years. The indexed Rs 3/2/1 per kg price is outdated and must not be given as current. [IDX-STALE][V]"),
("nfsa-gov-in#B", "AAY entitlement", "DET", "LAB", "L1", "EN", "S", "CITE", "P2",
 "How much grain does an Antyodaya card family get?",
 "35 kg of foodgrains per household per month, free of cost. [IDX][V]"),
("nfsa-gov-in#C", "DBT in food", "DET", "JOUR", "L2", "EN", "D", "CITE", "P2",
 "Where was Direct Benefit Transfer of food subsidy first started under NFSA?",
 "In the UTs of Chandigarh and Puducherry from September 2015, and in part of Dadra & Nagar Haveli from March 2016. [IDX]"),
("nfsa-gov-in#E", "UP ration complaint - State named", "STATE", "LAB", "L0", "HG", "S", "ROUTE", "P0",
 "UP me ration card ki shikayat kahan kare",
 "Named, not refused (G12): Department of Food and Civil Supplies, Uttar Pradesh - fcs.up.gov.in, grievance system "
 "cms.up.gov.in (from nfsa.gov.in State: Uttar Pradesh page). [IDX]"),
# ---- Passport Seva ----
("passportindia-gov-in#A", "Reschedule appointment", "PROC", "GRAD", "L1", "EN", "S", "CITE", "P0",
 "How many times can I reschedule my passport appointment?",
 "Three times; only once for a Tatkaal appointment (Passport Seva 'applyFor' page, updated 06-10-2026). [IDX]"),
("passportindia-gov-in#B", "Apply at passport office?", "PROC", "PEN", "L0", "HI", "W", "CITE", "P1",
 "नया पासपोर्ट बनवाना है, क्या मैं सीधे पासपोर्ट ऑफिस जा सकता हूं?",
 "No: fresh passport applications are submitted at a Passport Seva Kendra (PSK) or Post Office Passport Seva Kendra "
 "(POPSK), not at the Passport Office. [IDX]"),
("passportindia-gov-in#C", "What is a POPSK", "DET", "STU", "L0", "EN", "S", "CITE", "P2",
 "What is a POPSK?",
 "A Post Office Passport Seva Kendra - an extended arm of the Passport Office providing front-end services from token "
 "issue to granting the application. [IDX]"),
("passportindia-gov-in#D", "Passport helpline", "USE", "WID", "L0", "HG", "S", "CITE", "P1",
 "passport ka helpline number kya hai, status bhi pata chalega?",
 "Call centre 1800-258-1800 (status can be asked there), passportindia.gov.in, or the helpdesk at the nearest PSK. Cannot "
 "check the status itself. [IDX]"),
# ---- ECI ----
("eci-gov-in#A", "Download e-EPIC", "USE", "STU", "L0", "EN", "S", "CITE", "P1",
 "How can I download my voter ID card online?",
 "Download the e-EPIC from the electors services using the EPIC number or the form reference number. [IDX]"),
("eci-gov-in#B", "Correct voter ID error", "PROC", "TEA", "L1", "HI", "S", "CITE", "P0",
 "मेरे वोटर आईडी में नाम गलत छपा है, कैसे सुधरेगा?",
 "Apply in Form 8; after correction the ERO issues a new EPIC with the same number. [IDX]"),
("eci-gov-in#C", "Which voter form", "RULE", "NRI", "L1", "EN", "C", "CITE", "P1",
 "Which form do I use as an overseas voter, and which one links Aadhaar with my voter record?",
 "Form 6A for overseas electors; Form 6B for Aadhaar linking (roll authentication); Form 6 is new registration, Form 7 "
 "objection/deletion, Form 8 shifting/correction/replacement. [IDX]"),
("eci-gov-in#D", "Proxy voting deadline", "RULE", "EXS", "L2", "EN", "L", "CITE", "P2",
 "As a service voter, by when must my proxy appointment application reach the Returning Officer?",
 "Before the last date for filing nomination papers; a revocation takes effect from the date the Returning Officer "
 "receives it. [IDX]"),
# ---- Sarathi ----
("sarathi-parivahan-gov-in#A", "Renew DL online", "PROC", "SHOP", "L1", "HG", "S", "CITE", "P0",
 "driving licence renew kaise kare online",
 "sarathi.parivahan.gov.in > select State > 'Services on Drivers License (Renewal/Duplicate/AEDL/Others)' > fill the form > "
 "Next > visit the RTO on the scheduled date with originals and fee slip; if expired over 1 year a driving test or a "
 "learner's licence may be required. [IDX]"),
("sarathi-parivahan-gov-in#B", "Renewal window", "RULE", "PEN", "L1", "EN", "S", "CITE", "P1",
 "How early can I renew my driving licence before it expires?",
 "Within one year before or after expiry (CMV Act amendment); a commercial licence is valid 5 years from issue. [IDX]"),
("sarathi-parivahan-gov-in#C", "Learner test", "RULE", "SCH", "L0", "EN", "S", "CITE", "P1",
 "Do I have to pass a test to get a learner's licence?",
 "Yes - the online STALL test; sample questions are on Sarathi; report to the RTO or an authorised LL test centre. [IDX]"),
("sarathi-parivahan-gov-in#D", "Update mobile in DL", "PROC", "LAB", "L0", "HI", "S", "CITE", "P2",
 "ड्राइविंग लाइसेंस में मोबाइल नंबर कैसे बदलें?",
 "sarathi.parivahan.gov.in > select State > 'Others' menu > 'Mobile Number Update'. [IDX]"),
# ---- NSP ----
("scholarships-gov-in#A", "What is OTR", "DET", "STU", "L0", "HG", "S", "CITE", "P1",
 "nsp me OTR kya hota hai aur kaise banta hai",
 "One Time Registration: a unique number valid for the whole academic career on NSP, required from AY 2024-25, generated "
 "with Aadhaar or Aadhaar Enrolment ID; NSP OTR app on Google Play. [IDX]"),
("scholarships-gov-in#B", "Disability scholarship income limit", "RULE", "PWD", "L1", "EN", "S", "CITE", "P1",
 "What is the parental income limit for the scholarships for students with disabilities?",
 "Pre-Matric and Post-Matric: Rs 2.50 lakh a year; Top Class: Rs 8.00 lakh a year (all on NSP). [IDX]"),
("scholarships-gov-in#C", "SC Top Class scholarship", "DET", "SCH", "L1", "HI", "S", "CITE", "P1",
 "एससी छात्रों के लिए टॉप क्लास स्कॉलरशिप में आय सीमा क्या है? लड़कियों के लिए आरक्षण है?",
 "Family income up to Rs 8.00 lakh a year; admission in a notified institution; awarded on merit; 30% of slots reserved for "
 "SC girl students. [IDX]"),
("scholarships-gov-in#D", "AICTE Pragati duration", "RULE", "GRAD", "L1", "EN", "S", "CITE", "P2",
 "How long does the AICTE Pragati scholarship last and how is it renewed?",
 "Up to 4 years for degree and 3 years for diploma students; renewed each year on NSP with a promotion certificate "
 "certified by the head of institution. [IDX]"),
]),
]
