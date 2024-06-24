# Import necessary libraries
import json

import openai
import requests

from schemas.medical_info_inquiry import InquiryDetails
from services.azure_doc_intelligence import AzureDocIntelligence

# Set OpenAI API key
openai.api_key = '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'


# Helper function to fetch and parse content from URLs
def fetch_content(url):
    response = requests.get(url)
    return response.content


# Function to create a SRL document
def generate_report(inquiry_details, article_summaries):
    # Define the conversation with GPT

    title = inquiry_details.document_title
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        # Convert the inquiry to a text format
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)
    summary = inquiry_details.summary_section
    additional_notes = inquiry_details.additional_notes

    article_content = "{" + ", ".join([f"'{content}'" for content in article_summaries]) + "}"

    prompt = f"""You are a Medical Information Specialist working for a pharmaceutical company. Your role involves responding to clinical inquiries from healthcare professionals (HCPs) by providing accurate and comprehensive information based on the latest research and clinical data. Your task is to create a DETAILED document to answer Health Care Professional (HCP)-submitted clinical inquiry about a pharmaceutical company's drugs focusing on the inquiry type, and utilizing reference context for evidence-based information. 

    The inquiry MUST pertain to the area of {inquiry_type}, emphasizing the need for detailed analysis and evidence-based information. 

    Guidelines for document generation:
	
	Below are the context from which the document has to be generated, 
	
	HCP Inquiry: 
	Carefully review the HCP’s question or request. 
	Extract information that directly addresses the HCP’s inquiry "{inquiry}" which pertail to the inquiry type "{inquiry_type}"

	Summary Section: 
	Consider the user_service.py's summary input as additional context for the HCP's inquiry. 
	Use this summary to better understand what specific information the user_service.py is looking for and tailor the extraction process accordingly. 
	{summary}

	Additional Notes: 
	Consider any additional notes provided by the user_service.py for further context. 
	Extract relevant information that might be pertinent to the inquiry but does not fall under the specific categories listed above. 
	{additional_notes}

    -Input Article- :["{article_content}"]

    Read the entire article content provided above thoroughly and address the inquiry about pharmaceutical products.
	Follow the below guidelines to structure the document content with specified headers: 

    Title: 

    Document Title specified above. Concise, and formatted in title case with bolded text. {title}

    Overview 

    Detailed background information relevant to the inquiry. 
	Introduction to drug and its indications and description of the investigational usage. 
	Summarized paragraphs of titles - Introduction, Study design, Results/Discussion, Conclusion by thoroughly going through each data provided within the context  
    
    Summary 

    This content MUST have detailed description of the various phases of studies including the geographical scope and organizational setup of the study, details on the open-label/closed-label study design and dosages used in the study. Elaborate more on the various studies from the context. Presentation of the results, including the number of patients treated and metrics involved in vaious studies should also be elaborated. 
      
   Clinical Data 
   
	This part of the document plays the major part and MUST cover more DETAILED content on the clinical trials.
    This section MUST include the DETAILED description and explanation of the clinical trials from the article given. 
	This SHOULD include all the information of the clinical trials specific to the inquiry type {inquiry_type} and relevant to the HCP inquiry "{inquiry}". 
	It is MANDATORY to include the tabular representation of clinical data provided in the references. 
	Extract and create tables for the clinical trial data, ensuring all relevant data is captured and tables should be in MARKDOWN format. 
	This section MUST include the following data from the article,
      1. Description of the study design, including patient eligibility criteria, dosing schedules, and the study's objectives. 
      3. Detailed results of the study focussing more on the inquiry type - {inquiry_type} 
      4. Tabular representation of the clinical trial data. 

   Results 

    This section should include detailed description of the outcome, recommended dosage level, overall outcome measure, e.g., response rate (ORR), summary of the disease control rate, overview of the clinical benefit rate, drug Exposure Analysis, Analysis of how a specific factor (e.g., food) affects the drug's exposure and various other relevant data points. This should include discussion on clinical activity and genetic alterations in treated patients and also tabular representation of results achieved during various studies conducted. Incorporate the presentation of results across various metrics as a distinct subsection. 

  
    --- 



    Refer the example below. 

    *** Start of Examples *** 

	 HCP Input : 
	 HCP Inquiry: "Can ribociclib be used for patients with HR+, HER2- advanced breast cancer?" 

	Document Title: "Phase I Triplet Therapy (ribociclib+everolimus+exemestane) Study in HR+/HER2- Advanced Breast Cancer" 

	Summary Section: "The HCP is specifically interested in understanding the clinical outcomes. This includes data on overall response rates, progression-free survival, and common adverse events." 

	Inquiry Type: "Efficacy (Primary and Secondary Outcomes), Safety (General and Specific AEs)"

	Additional Notes: "In addition to the clinical outcomes, highlight the recommended phase II dose and any dose-limiting toxicities observed. Include pharmacokinetic data and relevant genetic alterations identified in the study." 
	

    Output: 

    Phase I Triplet Therapy (ribociclib+everolimus+exemestane) Study in HR+/HER2- Advanced Breast Cancer 


    Overview 

    Kisqali® (ribociclib), a kinase inhibitor, is indicated in combination with an aromatase inhibitor as initial endocrine-based therapy for the treatment of postmenopausal women with hormone receptor (HR)-positive, human epidermal growth factor receptor 2 (HER2)-negative advanced or metastatic breast cancer. [1]   Ribociclib in combination with everolimus and exemestane is investigational.  Efficacy and safety have not been established.  There is no guarantee that this combination will become commercially available for uses under investigation. 

    A triplet combination therapy study was conducted with ribociclib plus everolimus (EVE) plus exemestane (EXE) to assess the safety and preliminary efficacy results of from the ongoing Phase Ib (CLEE011X2106, NCT01857193) study in postmenopausal patients with HR+/HER2– advanced breast cancer (aBC) refractory to non-steroidal aromatase inhibitors (letrozole or anastrozole).  Results from the study are summarized below.  Potential predictive biomarkers of response were also explored. [2]  

    Summary 

    This was a Phase Ib, multicenter, open-label study, in which postmenopausal women with estrogen receptor-positive/human epidermal growth factor receptor 2-negative advanced breast cancer (ER+/HER2− aBC), who were resistant to letrozole or anastrozole, were treated with escalating doses of ribociclib (ranging from 200 to 350 mg), everolimus (EVE; 1 to 5 mg/day), and exemestane (EXE; 25 mg/day) in Arm 1, or with ribociclob (600 mg/day) and EXE (25 mg/day) in Arm 2. Out of a total of 91 patients treated, results from 77 patients treated with the triplet combination of ribociclib, EVE, and EXE were presented. Grade 3 dose-limiting toxicities were reported in eight patients treated with ribociclib (300 mg) plus EVE (2.5 mg). 

   The recommended Phase II dose (RP2D) was determined to be 300 mg/day of ribociclib (administered in a 3-weeks-on/1-week-off schedule), 2.5 mg/day of EVE (given continuously), and 25 mg/day of EXE (also given continuously), taken with food. Among the 77 evaluable patients, 7 (9%) achieved a partial response (PR), 39 (51%) exhibited stable disease (SD), and 10 (13%) showed neither complete response nor progressive disease (NCRNPD). No patient experienced a complete response (CR). The overall response rate (CR + PR) was 9% (n = 7; 95% confidence interval, 4 – 18%), and the disease control rate (CR + PR + SD + NCRNPD) was 73% (n = 56; 95% CI, 61 – 82%). The clinical benefit rate (defined as confirmed CR + PR + SD lasting ≥24 weeks + NCRNPD lasting ≥24 weeks) was 26% in 74 evaluable patients (n = 19; 95% CI, 16 – 37%). 

    Common hematologic adverse events associated with triplet therapy included neutropenia (31%), neutrophil count reduction (18%), and white blood cell count reduction (12%), all classified as Grade 3/4 study drug-related adverse events occurring in ≥10% of the patients. 

    Clinical Data 

    Study Design 

    In the dose-escalation part of this Phase Ib, multicenter, open-label study, postmenopausal women with ER+/HER2– aBC, refractory to letrozole or anastrozole, were treated with escalating doses of oral ribociclib (200 – 350 mg/day) + EVE (1 – 5 mg/day) + EXE (25 mg/day), or with ribociclib (600 mg/day) + EXE (25 mg/day).  Ribociclib was administered once daily for 3 weeks followed by a 1-week rest (28-day cycles); EVE and EXE were administered once daily on a continuous basis. [2]  

    Patients were treated until disease progression, development of unacceptable toxicity, or withdrawal of informed consent.  This study consisted of 2 cohorts of patients, either fasted or fed, prior to study drug administration to evaluate the effect of food on tolerability to study treatment.  After the maximum tolerated dose (MTD)/recommended phase II dose (RP2D) was determined, the dose-expansion part of this study assessed the tolerability and clinical efficacy of the triplet and doublet combinations at the RP2D in patients who were either naïve/refractory to CDK4/6 inhibitor-based therapy. [2]  

    The primary objective of the study was to determine the MTD/RP2D of ribociclib + EVE + EXE in patients with ER+/HER2– aBC.  Secondary objectives included determining the safety and tolerability of the regimens in both study arms; characterizing the pharmacokinetic (PK) profile of ribociclib and/or EVE when administered in combination with EXE in fed and fasted states; evaluating the preliminary antitumor activity of the regimens in both study arms; and assessment of the relationship between antitumor activity and genetic/pharmacodynamic biomarkers in the CDK4/6, PI3K/AKT/mTOR, and other cancer-related pathways. [2]  

    Key inclusion criteria included the following: postmenopausal women with ER+/HER2– locally advanced or metastatic BC; recurrence while on or within 12 months of end of adjuvant treatment with letrozole or anastrozole or progression while on or within 1 month of end of treatment with letrozole or anastrozole for locally advanced or metastatic BC; no letrozole or anastrozole prior to study; previous treatment with a CDK4/6 inhibitor, EXE, or mTOR inhibitor was allowed; and representative tumor specimen (archival or new) should have been available for molecular testing.  Key exclusion criteria included: >2 chemotherapy lines for aBC; active skin, mucosa, ocular, or gastrointestinal disorders of grade (G) >1; absolute neutrophil count <1.5 x 109/L; alanine aminotransferase (ALT) and aspartate aminotransferase (AST) ≥3 x upper limit of normal (ULN), or AST and ALT ≥5 x ULN if liver metastases were present; clinically significant cardiac disease. [2]  

    Safety assessments were conducted at baseline and at regular intervals throughout the study.  Tumor response was assessed locally by the investigator using computerized tomography or magnetic resonance imaging according to Response Evaluation Criteria In Solid Tumors (RECIST) v1.1.  Pharmacokinetic sampling was performed and tumor samples were analyzed determine any alterations in genes of interest. [2]  
  

    Results 

    As of August 21, 2015, at total of 91 patients had been treated, including 77 with the triplet combination of ribociclib, EVE and EXE.  The median number of prior regimens was four.  Prior chemotherapy and PI3K/AKT/mTOR inhibitors for advanced disease were received by 39 (51%) and 18 (23%) patients, respectively.  Treatment was discontinued in 57 (74%) patients due to: disease progression (n = 48: 62%), AEs (n = 5: 7%), withdrawal of consent (n = 3: 4%), or administrative problems (n = 1; 1%). [2]   

    Dose-limiting toxicities (DLTs) during Cycle 1 were observed in eight (12%) of 65 evaluable patients receiving triplet therapy (ribociclib 300 mg + EVE 2.5 mg + EXE fasted, n=4 [40%]; ribociclib 300 mg + EVE 2.5 mg + EXE fed, n = 3 [27%]; ribociclib 350 mg + EVE 2.5 mg + EXE fed, n = 1 [17%]).  Dose limiting toxicities included the following: G3 thrombocytopenia (n = 3), G3 alanine aminotransferase elevation (n = 2), G3 aspartate aminotransferase elevation (n = 2), G3 febrile neutropenia (n = 1), G1 hemoptysis (n = 1), G3 hypophosphatemia (n = 1), G4 neutrophil count decreased (n = 1), G3 rash (n = 1), and G3 stomatitis (n = 1). [2]  

    The RP2D for the triplet combination was determined to be 300 mg/day ribociclib (3-weeks-on/1-week-off) + 2.5 mg/day EVE (continuous) + 25 mg/day EXE (continuous) with food. [2]  

   Pharmacokinetics 

    Ribociclib steady-state exposure (maximum plasma concentration [Cmax] and area under the curve from time zero to 24 h [AUC0–24h]) in the presence of EVE and EXE had a dose-dependent increase and was within the range of exposures observed for single-agent ribociclib at similar doses.  EVE (2.5 mg) steady-state exposure generally increased with increasing ribociclib dose (200 – 350 mg). [2]   

    The mean steady-state exposure of ribociclib and EVE was slightly lower when given with food, although at the RP2D (300 mg ribociclib + 2.5 mg EVE + 25 mg/day EXE, fed) individual Cmax and AUC0–24h values mostly remained within the range observed for the corresponding dose in the fasted state. [2]  

    Clinical Activity and Genetic Alterations 

    All 77 patients who received triplet therapy with ribociclib, EVE, and EXE were evaluable for treatment response.  Seven patients (9%) had confirmed PRs, 39 (51%) had SD and 10 (13%) had NCRNPD.  No patient experienced CR. [2]   

    Three of the PRs, seven SD, and one NCRNPD were experienced in patients who received prior PI3K/AKT/mTOR inhibitors.  The median duration of SD was 115 days (range: 44 – 460), and 21 patients experienced SD for >4 cycles.  Durable SD was also observed in patients with prior exposure to PI3K/AKT/mTOR inhibitors (n = 11; median SD = 115 days; range: 54 – 279) or CDK4/6 inhibitors (n = 2; 108 and 148 days SD). [2]   

    The overall response rate (CR + PR) was 9% (n = 7; 95% CI, 4 – 18%) and the disease control rate (CR + PR + SD + NCRNPD) was 73% (n = 56; 95% CI, 61 – 82%).  The clinical benefit rate (confirmed CR + PR + SD ≥24 weeks + NCRNPD ≥24 weeks) was 26% in 74 evaluable patients (n = 19; 95% CI, 16 – 37%). [2]  

    The median (range) duration of treatment exposure was 6 (1 – 15) months and 4 (1 – 17) months in patients with (n = 11) and without (n = 48) CCND1-amplified tumors, respectively.  In patients that experienced PR and had available genetic data, alterations included: amplification or mutations of PIK3CA (n = 3); TP53 mutations (n = 2); amplification of MDM2 (n = 2); amplification of MYC (n = 2); ATM mutation (n = 2); as well as alterations in KRAS, EGFR, FGFR1, and ESR1 (n = 1 each). [2]  

    Safety 

    Hematologic adverse events were among the most common toxicities associated with triplet therapy.  The most common Grade 3/4 study drug-related adverse events (≥10%) were neutropenia (31%), neutrophil count reduction (18%) and white blood cell count reduction (12%). [2]  

    A total of 17 patients (23%) receiving ribociclib in combination with EVE and EXE experienced a QTcF >450 ms; 3 (4%) patients had a QTcF >480 ms and 2 (3%) patients had a QTcF >500 ms. [2]  

    Incidence of any grade adverse events in all patients receiving the RP2D with triplet therapy is described in the table below. [2]  

    Table. Incidence of Any Grade Adverse Events in all Patients Receiving RP2D with Ribociclib 
	

    *** End of Examples *** 
     

    *GUIDLINES- 
    1. Interpret ALL tables, figures, graphs and charts. 
    2. RETURN ALL pertinent information and details without missing out on anything crucial. 
    3. Provide only factual information. 
    4. DO NOT assume, make inferences or hallucinate any data. 
    5. Return the response as text with table in markdown format. 
    6. Ensure the generated response accurately addresses the HCP's inquiry  
    7. Include only the most RELEVANT information from the selected citations  
    8. Present the information in a clear and understandable manner for healthcare professionals 

    CRITICAL DATA REVIEW MANDATE: In your analysis and summarization process, it is imperative to meticulously review and incorporate a thorough, detailed, and concise Summary. This includes thoroughly reading and understanding each line of the provided text, ensuring no information is disregarded or overlooked. This step is non-negotiable and must be adhered to before proceeding to answer the inquiry. Failure to comply with this mandate will result in incomplete and inaccurate summaries, which is unacceptable. Always confirm that all pertinent information, as explicitly stated or provided in the context, has been fully considered into your summaries.  

    *IMPORTANT MANDATE-  
    - The article generated should contain the sections - Overview, Summary, Clinical Data, Results, References. The Overview section will be a summary of the Summary section (which will be most detailed). Make sure to use these sections in such cases to provide the summarized response for the given inquiry. Clinical Data section is the MOST MANDATORY part which will have detailed data on the various trials and their outcomes based on the inquiry type specified. INCLUDE any sub-sections required for better readability.

    - DO NOT return any comment or statement stating that the context does not contain explicit information or any such lines, Ex: endpoints were not explicitly reported in the provide in the context, etc. Return whatever data is available as a concise summary and do NOT comment as further data not available or so.* """

    with open("input.txt", "w") as file:
        file.write(prompt)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves responding to clinical inquiries from healthcare professionals (HCPs) by providing accurate and comprehensive information based on the latest research and clinical data."},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]

    print(prompt)
    # Generate the report using the OpenAI API
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )

    # Extract the content from the response
    srl_content = response['choices'][0]['message']['content']

    with open("srl_content.txt", "w") as file:
        file.write(srl_content)

    return srl_content


# Run the function to create the document
def generate_summary(inquiry_details, file_name):
    # Define the conversation with GPT
    print(inquiry_details)
    print(inquiry_details.inquiry_type)
    #title = inquiry_details.document_title
    inquiry = inquiry_details.inquiry
    inquiry_type = "All"
    if bool(inquiry_details.inquiry_type):
        # Convert the inquiry to a text format
        inquiry_type = convert_to_text_format(inquiry_details.inquiry_type)
    #summary = inquiry_details.summary_section
    #additional_notes = inquiry_details.additional_notes

    print("started...")
    azure = AzureDocIntelligence()
    print("Initializing...")
    doc_intell_response_obj, doc_intell_response_dict = azure.get_raw_output(
        local_inp_file_path=f"storage/data/{file_name}")

    processed_content = azure.get_processed_output(raw_output_obj=doc_intell_response_obj)
    processed_content.to_json("processed.json", orient="records", indent=4)

    with open("processed.json") as file:
        content_json = file.read()

    # Load the JSON string from the file
    article = json.dumps(content_json)
    prompt = f"""Create a DETAILED document to answer Health Care Professional (HCP)-submitted clinical inquiry {inquiry} about a pharmaceutical company's drugs focusing on the inquiry type, {inquiry_type} and utilizing reference context for evidence-based information. 

        The inquiry MUST pertain to the area of {inquiry_type}, emphasizing the need for detailed analysis and evidence-based information.
		Provide thorough and continuous explanations, ensuring clarity and depth suitable for advanced students. Avoid using summaries, bullet points, or any form of content organization that simplifies the information. The content SHOULD read like a detailed chapter from a textbook, providing in-depth knowledge without redundant or overlapping information from other modules.

        Guidelines for document generation: 

        context: [{article}]s

        Read the entire article content provided in the context above thoroughly and address the inquiry about pharmaceutical products.
		
		-The HCPs seek content that is THOROUGH and IN-DEPTH details on the Clinical data that answers the inquiry - {inquiry} . The content should avoid being overly summarized or simplified.
        
        - Detailed background information relevant to the inquiry. 
    	Introduction to drug and its indications and description of the investigational usage. 
    	Summarized paragraphs of titles - Introduction, Study design, Results/Discussion, Conclusion by thoroughly going through each data provided within the context  

		-This content MUST have detailed description of the various phases of studies including the geographical scope and organizational setup of the study, details on the open-label/closed-label study design and dosages used in the study. Elaborate more on the various studies from the context. Presentation of the results, including the number of patients treated and metrics involved in vaious studies should also be elaborated. 

        The content MUST include ALL the content related to clinical trials from the article given. 
        This should include all the information of the clinical trials specific to the inquiry type {inquiry_type}. 
        It is MANDATORY to include the tabular representation of clinical data provided in the references. 
		Extract and create tables for the clinical trial data in the markdown format.
        INCLUDE clinical trial ids specified in the context.

        This part of the document plays the major part and MUST cover more DETAILED content on the clinical trials. 
          1. Description of the study design, including patient eligibility criteria, dosing schedules, and the study's objectives. 
          3. Detailed results of the study focussing more on the inquiry type - {inquiry_type} 
          4. Tabular representation of the clinical trial data. 

        This content should include detailed description of the outcome, recommended dosage level, overall outcome measure, e.g., response rate (ORR), summary of the disease control rate, overview of the clinical benefit rate, drug Exposure Analysis, Analysis of how a specific factor (e.g., food) affects the drug's exposure and various other relevant data points. This should include discussion on clinical activity and genetic alterations in treated patients and also tabular representation of results achieved during various studies conducted. Incorporate the presentation of results across various metrics as a distinct subsection. 


        *GUIDLINES- 
        1. Interpret ALL tables, figures, graphs and charts. 
        2. RETURN ALL pertinent information and details without missing out on anything crucial. 
        3. Provide only factual information. 
        4. DO NOT assume, make inferences or hallucinate any data. 
        5. Return the response as text with table in markdown format. 
        6. Ensure the generated response accurately addresses the HCP's inquiry  
        7. Include only the most RELEVANT information from the selected citations  
        8. Present the information in a clear and understandable manner for healthcare professionals 

        CRITICAL DATA REVIEW MANDATE: In your analysis and summarization process, it is imperative to meticulously review and incorporate a thorough, detailed, and concise Summary. This includes thoroughly reading and understanding each line of the provided text, ensuring no information is disregarded or overlooked. This step is non-negotiable and must be adhered to before proceeding to answer the inquiry. Failure to comply with this mandate will result in incomplete and inaccurate summaries, which is unacceptable. Always confirm that all pertinent information, as explicitly stated or provided in the context, has been fully considered into your summaries.  

        *IMPORTANT MANDATE-  
        - The article generated should contain the sections - Overview, Summary, Clinical Data, Results, References. The Overview section will be a summary of the Summary section (which will be most detailed). Make sure to use these sections in such cases to provide the summarized response for the given inquiry. Clinical Data section is the MOST MANDATORY part which will have detailed data on the various trials and their outcomes based on the inquiry type specified. INCLUDE any sub-sections required for better readability.

        - DO NOT return any comment or statement stating that the context does not contain explicit information or any such lines, Ex: endpoints were not explicitly reported in the provide in the context, etc. Return whatever data is available as a concise summary and do NOT comment as further data not available or so.* """

    with open("input.txt", "w") as file:
        file.write(prompt)

    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role "
                    "involves responding to clinical inquiries from healthcare professionals (HCPs) by providing "
                    "accurate and comprehensive information based on the latest research and clinical data."},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]

    # Generate the report using the OpenAI API
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )

    # Extract the content from the response
    article_summary = response['choices'][0]['message']['content']

    with open("summary_content.txt", "w") as file:
        file.write(article_summary)

    return article_summary

# Function to convert the array to a text format
def convert_to_text_format(types):
    text = ""
    for inquiry_type in types:
        text += f"{inquiry_type.type} ({', '.join(inquiry_type.categories)}), "
    return text.rstrip(", ")  # Remove trailing comma and space


def generate_content(inquiry_details: InquiryDetails):
    summaries = []

    for filename in inquiry_details.document_source:
        article_summary = generate_summary(inquiry_details, filename)
        summaries.append(article_summary)

    srl_content = generate_report(inquiry_details, summaries)
    return srl_content