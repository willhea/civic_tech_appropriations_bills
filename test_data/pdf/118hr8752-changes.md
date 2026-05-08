# PDF Diff Test Cases — 118-HR-8752 v1→v2

Each case documents one change between the two PDF versions. Format:
- **Location:** `p.<page> L<line> – p.<page> L<line>` for both start and end (always include both pages, even if same).
  - Example single-page: `p.3 L8 – p.3 L11`
  - Example multi-page: `p.13 L21 – p.15 L11`
- Exact text as it appears in the PDF (paste as a single block; line breaks inside the ``` block are fine)
- Expected diff output (change type, anchor, what changed) — leave blank, I'll fill in
- Extraction notes — leave blank, I'll fill in after running pdfplumber

---

## Case 1 — OFFICE OF THE SECRETARY AND EXECUTIVE MANAGEMENT > Operations and Support

**Type:** modified — financial annotations added

**V1 location:** p.2 L14 – p.2 L25

**V1 text:**
```
For necessary expenses of the Office of the Secretary and for executive management
for operations and support, $281,358,000, of which $22,151,000 shall remain
available until September 30, 2026: Provided, That $5,000,000 shall be withheld
from obligation until the Secretary submits, to the Committees on Appropriations
of the House of Representatives and the Senate, responses to all questions for the
record for each hearing on the fiscal year 2026 budget submission for the
Department of Homeland Security held by such Committees prior to July 1: Provided
further, That not to exceed $30,000 shall be for official reception and
representation expenses.
```

**V2 location:** p.2 L12 – p.3 L2

**V2 text:**
```
For necessary expenses of the Office of the Secretary and for executive management
for operations and support, $281,358,000 (reduced by $20,000,000) (reduced by
$5,000,000) (increased by $10,000,000) (reduced by $10,000,000) (reduced by
$1,650,000) (reduced by $5,000,000) (reduced by $10,000,000), of which $22,151,000
shall remain available until September 30, 2026: Provided, That $5,000,000 shall
be withheld from obligation until the Secretary submits, to the Committees on
Appropriations of the House of Representatives and the Senate, responses to all
questions for the record for each hearing on the fiscal year 2026 budget submission
for the Department of Homeland Security held by such Committees prior to July 1:
Provided further, That not to exceed $30,000 shall be for official reception and
representation expenses.
```

**Expected diff output:**
- Change type: modified
- Anchor: OFFICE OF THE SECRETARY AND EXECUTIVE MANAGEMENT — Operations and Support
- What changed: financial annotations `(reduced by $20,000,000) (reduced by $5,000,000) (increased by $10,000,000) (reduced by $10,000,000) (reduced by $1,650,000) (reduced by $5,000,000) (reduced by $10,000,000)` inserted after `$281,358,000`
- Net: −$31,650,000

**Extraction notes:**
- pdfplumber captures the annotation chain correctly on v2 p.2 lines 14–17
- Line numbers (1, 2, 3…) appear on the left and must be stripped
- Page footer chrome (`•HR 8752 RH`, `VerDate` line, watermark) must be stripped
- Block spans a page boundary in v2 (p.2→p.3) — extractor must handle this
- V1 text layer spells all words correctly (`shall`, `responses`, `reception`, `representation`) — verify against visible PDF rendering

---

## Case 2 — MANAGEMENT DIRECTORATE > Operations and Support

**Type:** modified — financial annotations added

**V1 location:** p.3 L1 – p.3 L6


**V1 text:**
```
For  necessary  expenses  of  the  Management  Directorate  for  operations  and  support,  $1,637,290,000:  Provided, That not to exceed $2,000 shall be for official reception and representation expenses.
```

**V2 location:** p.3 L3 – p.3 L11

**V2 text:**
```
For  necessary  expenses  of  the  Management  Directorate  for  operations  and  support,  $1,637,290,000  (reduced  by  $3,000,000)  (reduced  by  $4,000,000)  (reduced by  $3,000,000)  (reduced  by  $15,000,000)  (reduced  by $5,000,000) (reduced by $3,000,000) (reduced by $18,168,000):  Provided,  That  not  to  exceed  $2,000  shall be for official reception and representation expenses.
```

**Expected diff output:**
- Change type: modified
- Anchor: MANAGEMENT DIRECTORATE — Operations and Support
- What changed: 7 reductions inserted after `$1,637,290,000`: −$3M, −$4M, −$3M, −$15M, −$5M, −$3M, −$18,168,000
- Net: −$51,168,000

**Extraction notes:**
- Block spans page boundary in v2 (annotations chain across multiple lines)
- pdfplumber may insert soft-hyphen breaks ("Direc-\ntorate", "(re-\nduced") that need rejoining

---

## Case 3 — MANAGEMENT DIRECTORATE > Procurement, Construction, and Improvements

**Type:** modified — financial annotations added (net zero)

**V1 location:** p.3 L8 – p.3 L11

**V1 text:**
```
For  necessary  expenses  of  the  Management  Directorate  for  procurement,  construction,  and  improvements, $54,337,000, to remain available until September 30, 2027.
```

**V2 location:** p.3 L13 – p.3 L17

**V2 text:**
```
For  necessary  expenses  of  the  Management  Directorate  for  procurement,  construction,  and  improvements, $54,337,000 (increased by $1,000,000) (reduced by $1,000,000), to remain available until September 30, 2027. 
```

**Expected diff output:**
- Change type: modified
- Anchor: MANAGEMENT DIRECTORATE — Procurement, Construction, and Improvements
- What changed: 2 offsetting annotations inserted after `$54,337,000`: +$1M, −$1M
- Net: $0 (offsetting — diff should still flag this since the text changed)

**Extraction notes:**
- Net-zero annotation pairs are a common pattern; the diff must surface them as modified, not unchanged

---

## Case 4 — SECURITY, ENFORCEMENT, AND INVESTIGATIONS > U.S. Customs and Border Protection > Operations and Support

**Type:** modified — financial annotations added

**V1 location:** p.11 L9 – p.12 L21

**V1 text:**
```
For  necessary  expenses  of  U.S.  Customs  and  Border Protection for operations and support, including the transportation  of  unaccompanied  alien  minors;  the  provision  of air and marine support to Federal, State, local, and international  agencies  in  the  enforcement  or  administration  of laws  enforced  by  the  Department  of  Homeland  Security; at  the  discretion  of  the  Secretary  of  Homeland  Security, the  provision  of  such  support  to  Federal,  State,  and  local agencies in other law enforcement and emergency humanitarian  efforts;  the  purchase  and  lease  of  up  to  7,500 (6,500  for  replacement  only) police-type  vehicles;  the  purchase,  maintenance,  or  operation  of  marine  vessels,  aircraft,  and  unmanned  aerial  systems;  and  contracting  with individuals for personal services abroad; $16,566,247,000; of  which  $3,274,000  shall  be  derived  from  the  Harbor Maintenance  Trust  Fund  for  administrative  expenses  related to the collection of the Harbor Maintenance Fee pursuant  to  section  9505(c)(3)  of  the  Internal  Revenue  Code of  1986  (26  U.S.C.  9505(c)(3))  and  notwithstanding  section  1511(e)(1)  of  the  Homeland  Security  Act  of  2002  (6 U.S.C.  551(e)(1));  of  which  $550,000,000  shall  be  available  until  September  30,  2026;  and  of  which  such  sums as become available in the Customs User Fee Account, except  sums  subject  to  section  13031(f)(3)  of  the  Consolidated  Omnibus  Budget  Reconciliation  Act  of  1985  (19 U.S.C. 58c(f)(3)), shall be derived from that account: Provided,  That  not  to  exceed  $34,425  shall  be  for  official  reception and representation expenses: Provided further, That  not  to  exceed  $150,000  shall  be  available  for  payment  for  rental  space  in  connection  with  preclearance  operations:  Provided  further,  That  not  to  exceed  $2,000,000 shall  be  for  awards  of  compensation  to  informants,  to  be  accounted  for  solely  under  the  certificate  of  the  Secretary of  Homeland  Security:  Provided  further,  That  not  to  exceed  $2,500,000  may  be  transferred  to  the  Bureau  of  Indian  Affairs  for  the  maintenance  and  repair  of  roads  on  Native American reservations used by the U.S. Border Patrol.
```

**V2 location:** p.11 L16 – p.13 L7

**V2 text:**
```
For  necessary  expenses  of  U.S.  Customs  and  Border Protection for operations and support, including the transportation  of  unaccompanied  alien  minors;  the  provision  of air and marine support to Federal, State, local, and international  agencies  in  the  enforcement  or  administration  of laws  enforced  by  the  Department  of  Homeland  Security; at  the  discretion  of  the  Secretary  of  Homeland  Security, the  provision  of  such  support  to  Federal,  State,  and  local agencies in other law enforcement and emergency humanitarian  efforts;  the  purchase  and  lease  of  up  to  7,500 (6,500  for  replacement  only)  police-type  vehicles;  the  purchase,  maintenance,  or  operation  of  marine  vessels,  aircraft,  and  unmanned  aerial  systems;  and  contracting  with individuals  for  personal  services  abroad;  $16,566,247,000 (reduced  by  $1,000,000)  (increased  by  $1,000,000)  (increased  by  $10,000,000)  (reduced  by  $10,000,000)  (reduced by $1,000,000) (increased by $1,000,000) (reduced by  $1,000,000)  (increased  by  $1,000,000)  (increased  by $5,000,000);  of  which  $3,274,000  shall  be  derived  from the  Harbor  Maintenance  Trust  Fund  for  administrative expenses  related  to  the  collection  of  the  Harbor  Maintenance  Fee  pursuant  to  section  9505(c)(3)  of  the  Internal Revenue  Code  of  1986  (26  U.S.C.  9505(c)(3))  and  notwithstanding section 1511(e)(1) of the Homeland Security Act  of  2002  (6  U.S.C.  551(e)(1));  of  which  $550,000,000 shall  be  available  until  September  30,  2026;  and  of  which such  sums  as  become  available  in  the  Customs  User  Fee Account, except sums subject to section 13031(f)(3) of the Consolidated  Omnibus  Budget  Reconciliation  Act  of  1985 (19  U.S.C.  58c(f)(3)),  shall  be  derived  from  that  account: Provided,  That  not  to  exceed  $34,425  shall  be  for  official reception  and  representation  expenses:  Provided  further, That  not  to  exceed  $150,000  shall  be  available  for  payment  for  rental  space  in  connection  with  preclearance  operations:  Provided  further,  That  not  to  exceed  $2,000,000 shall  be  for  awards  of  compensation  to  informants,  to  be accounted  for  solely  under  the  certificate  of  the  Secretary of  Homeland  Security:  Provided  further,  That  not  to  exceed  $2,500,000  may  be  transferred  to  the  Bureau  of  Indian  Affairs  for  the  maintenance  and  repair  of  roads  on Native American reservations used by the U.S. Border Patrol.
```

**Expected diff output:**
- Change type: modified
- Anchor: SECURITY, ENFORCEMENT, AND INVESTIGATIONS > U.S. Customs and Border Protection — Operations and Support
- What changed: 9 annotations inserted after `$16,566,247,000`: −$1M, +$1M, +$10M, −$10M, −$1M, +$1M, −$1M, +$1M, +$5M
- Net: +$5,000,000

**Extraction notes:**
- **PDF extraction artifact:** v2 text contains "(reducedby $1,000,000)" with no space between "reduced" and "by". This is a real pdfplumber bug from a hyphenated line break ("re-\nduced by") collapsed without a separator. Cleanup must handle this.
- Long block spans 2+ pages in both versions
- pdfplumber inserts a space mid-word in v2 ("not withstanding" should be "notwithstanding") — another line-break artifact

---

## Case 5 — SECURITY, ENFORCEMENT, AND INVESTIGATIONS > U.S. Customs and Border Protection > Procurement, Construction, and Improvements

**Type:** modified — financial annotations added

**V1 location:** p.12 L23 – p.13 L4

**V1 text:**
```
For  necessary  expenses  of  U.S.  Customs  and  Border Protection  for  procurement,  construction,  and  improvements,  including  procurement  of  marine  vessels,  aircraft, and  unmanned  aerial  systems,  $1,390,338,000,  of  which $766,684,000  shall  remain  available  until  September  30, 2027,  and  of  which  $623,654,000  shall  remain  available until September 30, 2029. 
```

**V2 location:** p.13 L9 – p.13 L18

**V2 text:**
```
For  necessary  expenses  of  U.S.  Customs  and  Border Protection  for  procurement,  construction,  and  improvements,  including  procurement  of  marine  vessels,  aircraft, and  unmanned  aerial  systems,  $1,390,338,000  (increased by  $4,000,000)  (increased  by  $10,000,000)  (reduced  by $10,000,000) (reduced by $1,000,000) (increased by $1,000,000),  of  which  $766,684,000  shall  remain  available until September 30, 2027, and of which $623,654,000  shall  remain  available  until  September  30, 2029.
```

**Expected diff output:**
- Change type: modified
- Anchor: SECURITY, ENFORCEMENT, AND INVESTIGATIONS > U.S. Customs and Border Protection — Procurement, Construction, and Improvements
- What changed: 5 annotations inserted after `$1,390,338,000`: +$4M, +$10M, −$10M, −$1M, +$1M
- Net: +$4,000,000

**Extraction notes:**
- Mixed offsetting/non-offsetting annotation cluster

---

## Case 6 — SECURITY, ENFORCEMENT, AND INVESTIGATIONS > U.S. immigration and customs enforcement > OPERATIONS AND SUPPORT

**Type:** modified — financial annotations added AND non-financial text change

**V1 location:** p.13 L7 – p.14 L20

**V1 text:**
```
For necessary expenses of U.S. Immigration and Customs  Enforcement  for  operations  and  support,  including  the  purchase  and  lease  of  up  to  3,790  (2,350  for  replacement only) police-type vehicles; overseas vetted units; and maintenance, minor construction, and minor leasehold improvements at owned and leased facilities; $10,497,243,000;  of  which  not  less  than  $6,000,000  shall remain available until expended for efforts to enforce laws against  forced  child  labor;  of  which  $46,696,000  shall  remain available until September 30, 2026; of which not less than  $2,000,000  is  for  paid  apprenticeships  for  participants in the Human Exploitation Rescue Operative Child-Rescue Corps;  of  which  not  less  than  $15,000,000  shall be available for investigation of intellectual property rights violations,  including  operation  of  the  National  Intellectual Property  Rights  Coordination  Center;  and  of  which  not less  than  $5,900,389,000  shall  be  for  enforcement,  detention,  and  removal  operations,  including  transportation  of unaccompanied alien minors, of which not less than $3,081,725,000 shall remain available until September 30, 2026:  Provided,  That  not  to  exceed  $11,475  shall  be  for official  reception  and  representation  expenses:  Provided further,  That not to exceed $10,000,000 shall be available until  expended  for  conducting  special  operations  under section 3131 of the Customs Enforcement Act of 1986 (19 U.S.C. 2081): Provided further, That not to exceed $2,000,000 shall be for awards of compensation to informants,  to  be  accounted  for  solely  under  the  certificate  of the Secretary of Homeland Security: Provided further, That not to exceed $11,216,000 shall be available to fund or  reimburse  other  Federal  agencies  for  the  costs  associated with the care, maintenance, and repatriation of smuggled  aliens  unlawfully  present  in  the  United  States: Provided  further,  That  not  less  than  $2,000,000  shall  be for entering into new agreements for the delegation of law enforcement  authority  provided  by  section  287(g)  of  the Immigration  and  Nationality  Act:  Provided  further,  That funding  made  available  under  this  heading  shall  maintain a level of not less than 50,000 detention beds.
```

**V2 location:** p.13 L21 – p.15 L11

**V2 text:**
```
For necessary expenses of U.S. Immigration and Customs  Enforcement  for  operations  and  support,  including  the  purchase  and  lease  of  up  to  3,790  (2,350  for  replacement only) police-type vehicles; overseas vetted units; and maintenance, minor construction, and minor leasehold improvements at owned and leased facilities; $10,497,243,000  (increased  by  $4,000,000)  (increased  by $2,000,000); of which not less than $6,000,000 (increased by  $4,000,000)  shall  remain  available  until  expended  for efforts to enforce laws against forced child labor; of which $46,696,000  shall  remain  available  until  September  30, 2026;  of  which  not  less  than  $2,000,000  (increased  by $2,000,000)  is  for  paid  apprenticeships  for  participants in  the  Human  Exploitation  Rescue  Operative  Child-Rescue  Corps;  of  which  not  less  than  $15,000,000  shall  be available  for  investigation  of  intellectual  property  rights violations,  including  operation  of  the  National  Intellectual Property  Rights  Coordination  Center;  and  of  which  not less  than  $5,900,389,000  shall  be  for  enforcement,  detention,  and  removal  operations,  including  transportation  of unaccompanied alien minors, of which not less than $3,081,725,000 shall remain available until September 30, 2026:  Provided,  That  not  to  exceed  $11,475  shall  be  for official  reception  and  representation  expenses:  Provided further,  That not to exceed $10,000,000 shall be available until  expended  for  conducting  special  operations  under section 3131 of the Customs Enforcement Act of 1986 (19 U.S.C. 2081): Provided further, That not to exceed $2,000,000 shall be for awards of compensation to informants,  to  be  accounted  for  solely  under  the  certificate  of the Secretary of Homeland Security: Provided further, That not to exceed $11,216,000 shall be available to fund or  reimburse  other  Federal  agencies  for  the  costs  associated with the care, maintenance, and repatriation of smuggled  aliens  unlawfully  present  in  the  United  States: Provided  further,  That  not  less  than  $2,000,000  shall be for entering into new agreements for the delegation of law enforcement  authority  provided  by  section  287(g)  of  the Immigration  and  Nationality  Act:  Provided  further,  That funding  made  available  under  this  heading  shall  maintain a level of not less than 50,000 detention beds. 
```

**Expected diff output:**
- Change type: modified
- Anchor: SECURITY, ENFORCEMENT, AND INVESTIGATIONS > U.S. Immigration and Customs Enforcement — Operations and Support
- What changed:
  - Top-level financial annotations after `$10,497,243,000`: +$4M, +$2M
  - Sub-amount annotation on `$6,000,000` line (forced child labor): +$4M
  - Sub-amount annotation on `$2,000,000` line (apprenticeships): +$2M
  - **Non-financial text change:** "Human Exploitation Rescue Operative Child Rescue Corps" (v1) → "Human Exploitation Rescue Operative Child-Rescue Corps" (v2). Hyphen added.
- Net (top-level): +$6,000,000 (sub-amount annotations are floor amendments to specific carve-outs, not changes to the top-line)

**Extraction notes:**
- This case demonstrates that annotations appear on sub-amounts within a single appropriation, not just top-level amounts
- The hyphen change is the only non-financial difference; word-diff must catch it
- Block spans 2+ pages

---

## Case 7 — SECURITY, ENFORCEMENT, AND INVESTIGATIONS > Transportation security administration > OPERATIONS AND SUPPORT

**Type:** modified — financial annotations added (net zero)

**V1 location:** p.15 L5 – p.15 L19

**V1 text:**
```
For  necessary  expenses  of  the  Transportation  Security Administration for operations and support, $10,817,225,000, of which $300,000,000 shall remain available  until  September  30,  2026:  Provided,  That  not to  exceed  $7,650  shall  be  for  official  reception  and  representation expenses: Provided  further,  That security service fees authorized under section 44940 of title 49, United States Code, shall be credited to this appropriation as offsetting  collections  and  shall  be  available  only  for  aviation security: Provided further, That the sum appropriated under this heading from the general fund shall be reduced on  a dollar-for-dollar  basis  as  such  offsetting  collections are  received  during  fiscal  year  2025  so  as  to  result  in  a final  fiscal  year  appropriation  from  the  general  fund  estimated at not more than $7,957,225,000.
```

**V2 location:** p.15 L21 – p.16 L11

**V2 text:**
```
For  necessary  expenses  of  the  Transportation  Security Administration for operations and support, $10,817,225,000  (increased  by  $50,000,000)  (reduced  by $50,000,000),  of  which  $300,000,000  shall  remain  available  until  September  30,  2026:  Provided,  That  not  to  exceed  $7,650  shall  be  for  official  reception  and  representation  expenses:  Provided  further,  That  security  service  fees authorized  under  section  44940  of  title  49,  United  States Code,  shall  be  credited  to  this  appropriation  as  offsetting collections and shall be available only for aviation security: Provided  further,  That  the  sum  appropriated  under  this heading  from  the  general  fund  shall  be  reduced  on  a  dollar-for-dollar  basis  as  such  offsetting  collections  are  received  during  fiscal  year  2025  so  as  to  result  in  a  final fiscal  year  appropriation  from  the  general  fund  estimated at not more than $7,957,225,000.
```

**Expected diff output:**
- Change type: modified
- Anchor: SECURITY, ENFORCEMENT, AND INVESTIGATIONS > Transportation Security Administration — Operations and Support
- What changed: 2 offsetting annotations after `$10,817,225,000`: +$50M, −$50M
- Net: $0

**Extraction notes:**
- Net-zero pair — diff must surface as modified, not unchanged

---

## Case 8 — SECURITY, ENFORCEMENT, AND INVESTIGATIONS > Transportation security administration > PROCUREMENT, CONSTRUCTION, AND IMPROVEMENTS

**Type:** modified — financial annotations added (net zero)

**V1 location:** p.15 L21 – p.15 L24

**V1 text:**
```
For  necessary  expenses  of  the  Transportation  Security  Administration  for  procurement,  construction,  and improvements,  $198,428,000,  to  remain  available  until September 30, 2027.
```

**V2 location:** p.16 L13 – p.16 L18

**V2 text:**
```
For  necessary  expenses  of  the  Transportation  Security  Administration  for  procurement,  construction,  and improvements,  $198,428,000  (reduced  by  $35,000,000) (increased  by  $35,000,000)  (reduced  by  $5,000,000)  (increased  by  $5,000,000),  to  remain  available  until  September 30, 2027.
```

**Expected diff output:**
- Change type: modified
- Anchor: SECURITY, ENFORCEMENT, AND INVESTIGATIONS > Transportation Security Administration — Procurement, Construction, and Improvements
- What changed: 4 offsetting annotations after `$198,428,000`: −$35M, +$35M, −$5M, +$5M
- Net: $0

**Extraction notes:**
- All-offsetting net-zero cluster

---

## Case 9 — RESEARCH, DEVELOPMENT, TRAINING, AND SERVICES > Administrative provisions > sec. 406

**Type:** modified — policy language only (no financial change)

**V1 location:** p.61 L5 – p.61 L19

**V1 text:**
```
SEC.  406.  Notwithstanding  the  numerical  limitation set forth  in  section  214(g)(1)(B)  of  the  Immigration  and Nationality  Act  (8  U.S.C.  1184(g)(1)(B)),  the  Secretary of  Homeland  Security,  after  consultation  with  the  Secretary  of  Labor,  and  upon  determining  that  the  needs  of American businesses cannot be satisfied during fiscal year 2025  with  United  States  workers  who  are  willing,  qualified, and able to perform temporary nonagricultural labor, shall  increase  the  total  number  of  visas  available  to  qualifying  aliens  under  section  101(a)(15)(H)(ii)(b)  of  such Act  (8  U.S.C.  1101(a)(15)(H)(ii)(b))  in  such  fiscal  year above such limitation by the highest number of H–2B nonimmigrants who participated in the H–2B returning worker  program  in  any  fiscal  year  in  which  returning  workers were exempt from such numerical limitation.
```

**V2 location:** p.62 L23 – p.63 L12

**V2 text:**
```
SEC.  406.  Notwithstanding  the  numerical  limitation set  forth  in  section  214(g)(1)(B)  of  the  Immigration  and Nationality  Act  (8  U.S.C.  1184(g)(1)(B)),  the  Secretary of  Homeland  Security,  after  consultation  with  the  Secretary  of  Labor,  and  upon  determining  that  the  needs  of American businesses cannot be satisfied during fiscal year 2025  with  United  States  workers  who  are  willing,  qualified, and able to perform temporary nonagricultural labor, may  increase  the  total  number  of  aliens  who  may  receive a  visa  under  section  101(a)(15)(H)(ii)(b)  of  such  Act  (8 U.S.C.  1101(a)(15)(H)(ii)(b))  in  such  fiscal  year  above such  limitation  by  not  more  than  the  highest  number  of H– 2B  nonimmigrants  who  participated  in  the  H–2B  returning worker program in any fiscal year in which returning  workers  were  exempt  from  such  numerical  limitation.
```

**Expected diff output:**
- Change type: modified — policy language only (no financial change)
- Anchor: RESEARCH, DEVELOPMENT, TRAINING, AND SERVICES > Administrative Provisions > SEC. 406
- What changed: three word-level edits weakening the Secretary's obligation:
  1. `shall increase` → `may increase`
  2. `total number of visas available to qualifying aliens` → `total number of aliens who may receive a visa`
  3. `by the highest number` → `by not more than the highest number`

**Extraction notes:**
- Pure text change, no dollar amounts — diff must catch this without relying on financial-line heuristics
- Section moved between pages (p.61 in v1 → p.62-63 in v2) as a side-effect of v2 being longer
- pdfplumber inserts a stray space inside `H– 2B` in v2 (line break artifact); cleanup must handle this

---

## Case 10 — RESEARCH, DEVELOPMENT, TRAINING, AND SERVICES > Administrative provisions > sec. 413

**Type:** removed

**V1 location:** p.63 L11 – p.63 L16

**V1 text:**
```
SEC.  413.  In  fiscal  year  2025,  nonimmigrants  shall be admitted to the United States under section 101(a)(15)(H)(ii)(a)  of  the  Immigration  and  Nationality Act (8  U.S.C.  1101(a)(15)(H)(ii)(a))  to  perform  agricultural  labor  or  services,  without  regard  to  whether  such labor is, or services are, of a temporary or seasonal nature.
```

**V2 location:** N/A (section removed)

**V2 text:**
```
(none — removed in v2)
```

**Expected diff output:**
- Change type: removed
- Anchor: RESEARCH, DEVELOPMENT, TRAINING, AND SERVICES > Administrative Provisions > SEC. 413 (v1 numbering)
- What changed: entire section removed. The H-2A agricultural worker waiver allowing year-round (non-seasonal) admission is dropped from the engrossed text.

**Extraction notes:**
- Possible alignment confusion with Case 13: in v2, a different provision occupies SEC. 413 (renumbered from v1's SEC. 414). The diff must not match this removed section to v2's SEC. 413 just because the section number matches — text similarity is the right signal here, not section number.

---

## Case 11 — GENERAL PROVISIONS > SPENDING REDUCTION ACCOUNT > sec. 558

**Type:** added

**V1 location:** N/A (new section in v2)

**V1 text:**
```
(none — added in v2)
```

**V2 location:** p.100 L23 – p.100 L25

**V2 text:**
```
SEC.  558.  None  of  the  funds  made  available  by  this Act  may  be  used  for  the  Inclusion  Action  Committee  of the Transportation Security Administration.
```

**Expected diff output:**
- Change type: added
- Anchor: GENERAL PROVISIONS > SEC. 558
- What changed: new policy rider prohibiting use of funds for the TSA Inclusion Action Committee.

**Extraction notes:**
- Short single-sentence section; tests the simple "added" path
- v2 has 6 more pages than v1 because of this added block (553-567); page-level alignment will fail for everything past p.96 — anchor/SEC.-based alignment is required

---

## Case 12 — GENERAL PROVISIONS > SPENDING REDUCTION ACCOUNT > sec. 553

**Type:** added

**V1 location:** N/A (new section in v2)

**V1 text:**
```
(none — added in v2)
```

**V2 location:** p.97 L15 – p.100 L6

**V2 text:**
```
SEC.  553.  (a)  None  of  the  funds  made  available  by this Act may be used - (1) to reduce the hours of operation at - (A)  the  Port  of  Carbury,  North  Dakota, port  of  entry  from  the  operational  hours  of  9:00 AM to 10:00 PM CT daily; (B)  the  Port  of  Fortuna,  North  Dakota, port  of  entry  from  the  operational  hours  of  9:00 AM to 10:00 PM CT daily; (C)  the  Port  of  Madia,  North  Dakota,  port of  entry  from  the  operational  hours  of  9:00  AM to 10:00 PM CT daily; (D)  the  Port  of  Neche,  North  Dakota,  port of  entry  from  the  operational  hours  of  8:00  AM to 10:00 PM CT daily; (E)  the  Port  of  Noonan,  North  Dakota, port  of  entry  from  the  operational  hours  of  9:00 AM to 10:00 PM CT daily; (F)  the  Port  of  Northgate,  North  Dakota, port  of  entry  from  the  operational  hours  of  9:00 AM to 10:00 PM CT daily; (G)  the  Port  of  Saint  John,  North  Dakota, port  of  entry  from  the  operational  hours  of  8:00 AM to 9:00 PM CT daily; (H)  the  Port  of  Sherwood,  North  Dakota, port  of  entry  from  the  operational  hours  of  9:00 AM to 10:00 PM CT daily; (I)  the  Port  of  Walhalla,  North  Dakota, port  of  entry  from  the  operational  hours  of  8:00 AM to 10:00 PM CT daily; (J)  the  Port  of  Westhope,  North  Dakota, port  of  entry  from  the  operational  hours  of  8:00 AM to 9:00 PM CT daily; (K)  the  Port  of  Antler,  North  Dakota,  port of  entry  from  the  operational  hours  of  9:00  AM to 10:00 PM CT daily; (L)  the  Port  of  Sarles,  North  Dakota,  port of  entry  from  the  operational  hours  of  11:00 AM to 7:00 PM CT daily; (M) the Port of Lancaster, Minnesota, port of  entry  from  the  operational  hours  of  8:00  AM to 10:00 PM CT daily; (N)  the  Port  of  Roseau,  Minnesota,  port  of entry  from  the  operational  hours  of  8:00  AM  to 12:00 AM CT daily; (O)  the  Porthill,  Idaho,  land  Port  of  entry, from  the  operational  hours  of  7:00  AM  to  11:00 PM PT daily; or (P)  the  Port  of  Buffalo,  New  York,  port  of entry  from  the  operational  hours  of  7:00  AM  to 12:00AM ET daily; (2) to implement, administer, enforce, carry out,  or  execute  any  rules,  guidance,  decisions,  announcements, or promulgations that reduce or change  the  hours  of  operation  at  the  ports  of  entry  specified in paragraph (1); or (3)  to  publish,  promulgate,  or  otherwise  issue rules,  guidance,  decisions,  announcements,  or  promulgations  that  reduce  or  change  the  hours  of  operation  at  the  ports  of  entry  specified  in  paragraph (1). (b)  The  limitation  described  in  paragraph  (1)  may not be construed to apply in the case of the administration of a tax or tariff.
```

**Expected diff output:**
- Change type: added
- Anchor: GENERAL PROVISIONS > SEC. 553
- What changed: new section prohibiting reduction of operating hours at 16 listed ports of entry (mostly North Dakota, plus Minnesota, Idaho, New York), with related rulemaking restrictions and a tax/tariff carve-out.

**Extraction notes:**
- Long block (~3 pages) with hierarchical structure: (a)(1)(A) through (a)(1)(P), (a)(2), (a)(3), (b)
- Tests that long added blocks render readably, not as one wall of text
- pdfplumber may produce odd spacing inside hour ranges (e.g., `9:00 AM` vs `9:00AM`); cleanup must normalize
- Subsection (b) refers to "paragraph (1)" but means subsection (a)(1) — text quirk in the bill itself, not an extraction issue

---

## Case 13 — RESEARCH, DEVELOPMENT, TRAINING, AND SERVICES > Administrative provisions > sec. 414→413 (renumbered)

**Type:** moved

**V1 location:** p.63 L17 – p.63 L22

**V1 text:**
```
SEC.  414.  None  of  the  funds  made  available  in  this Act  may  be  made  available  to  implement,  administer,  or  enforce  the  "Asylum  Program  Fee"  from  the  Final  Rule entitled  "U.S.  Citizenship  and  Immigration  Services  Fee Schedule and Changes to Certain Other Immigration Benefit Request Requirements" (88 Fed. Reg. 6194). 
```

**V2 location:** p.65 L4 – p.65 L9

**V2 text:**
```
SEC.  413.  None  of  the  funds  made  available  in  this Act  may  be  made  available  to  implement,  administer,  or enforce  the  "Asylum  Program  Fee"  from  the  Final  Rule entitled  "U.S.  Citizenship  and  Immigration  Services  Fee Schedule and Changes to Certain Other Immigration Benefit Request Requirements" (88 Fed. Reg. 6194).
```

**Expected diff output:**
- Change type: moved (renumbered) — content essentially unchanged
- Anchor: RESEARCH, DEVELOPMENT, TRAINING, AND SERVICES > Administrative Provisions
- What changed: section number changed from `SEC. 414` (v1) to `SEC. 413` (v2); the substantive text (Asylum Program Fee prohibition) is identical except for a closing-quote glyph difference (see notes).

**Extraction notes:**
- v1 has `Requirements'’` (smart-quote followed by straight apostrophe) and v2 has `Requirements’’` (two smart-quotes). This is almost certainly a typo that was corrected, not a substantive change. The diff should treat this as "moved/unchanged" rather than "modified" — we don't want quote-glyph differences flagged as content changes.
- Section number is part of the text, so naive text-similarity will see "414" vs "413" and may classify as modified rather than moved. The diff must normalize section numbers (or compare body text without the SEC. N. prefix) to detect renumbering.
- This is the trickiest case in the set; flag as a known limitation if the extractor can't handle it cleanly in the prototype.
