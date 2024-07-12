import concurrent

import openai
import json
import datetime
import aiohttp
from lxml import etree
from config import settings

openai.api_key = settings.env.open_ai_key

async def fetch_articles_based_on_inquiry(inquiry):
    pubmed_article_ids = await esearch(inquiry)
    articles_json = await get_pubmed_article(pubmed_article_ids)
    return json.loads(articles_json)


async def esearch(inquiry):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": inquiry.inquiry,
        "retmax": 50
    }
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    # Parse the XML response
                    tree = etree.fromstring(await response.read())

                    # Extract the IDs
                    ids = tree.xpath('//Id/text()')
                    return ids
                else:
                    raise Exception(f"Failed to fetch search results: {response.status}")
        except Exception as e:
            print(f"An error occurred: {e}")
            raise


async def get_pubmed_article(pubmed_ids):
    # Construct the URL for fetching the articles
    article_url = f"http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&tool=PMA&id={','.join(pubmed_ids)}"

    # Send the GET request asynchronously
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.get(article_url) as response:
            if response.status == 200:
                root = etree.fromstring(await response.text())
                articles = []

                # Use ThreadPoolExecutor to process articles in parallel
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Map each article_element to the process_article_element function
                    futures = [executor.submit(process_article_element, article_element) for article_element in
                               root.iter('PubmedArticle')]

                    # Collect the results from all futures
                    for future in concurrent.futures.as_completed(futures):
                        article_dict = future.result()
                        articles.append(article_dict)

                # Convert the list of dictionaries to JSON
                json_data = json.dumps(articles, indent=4)
                return json_data
            else:
                raise Exception(f"Failed to fetch PubMed articles: {response.status}")

def get_summary(abstract):
    prompt = f"SUMMARIZE the following Pubmed article abstract: {abstract} into a brief description that is EXACTLY within 500 characters long."
    conversation = [
        {"role": "system",
         "content": "You are a Medical Information Specialist working for a pharmaceutical company. Your role involves summarizing the abstract data of the Pubmed Article"},
        {"role": "user", "content": f"""{prompt}"""
         }
    ]
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=conversation,
        temperature=0,
        max_tokens=4096
    )
    summary = response['choices'][0]['message']['content']
    return summary

def process_article_element(article_element):
    # Initialize variables
    id = ""
    title = ""
    abstract = ""
    url = ""
    author = ""
    affiliation = []
    formatted_date = ""
    publication_type = []
    journal_title = ""
    keywords = []

    # Populate variables based on the existence of elements
    if article_element.find('./MedlineCitation/PMID') is not None:
        id = article_element.find('./MedlineCitation/PMID').text
        url = f"https://pubmed.ncbi.nlm.nih.gov/{id}/"

    if article_element.find('./MedlineCitation/Article/ArticleTitle') is not None:
        title = article_element.find('./MedlineCitation/Article/ArticleTitle').text

    if article_element.find('./MedlineCitation/Article/Abstract/AbstractText') is not None:
        abstractText = article_element.find('./MedlineCitation/Article/Abstract/AbstractText').text

        if abstractText is not None and len(abstractText) > 600:
            abstract = get_summary(abstractText)  # Assuming get_summary is defined elsewhere
        else:
            abstract = abstractText

    if article_element.find('./MedlineCitation/Article/AuthorList/Author') is not None:
        authors = article_element.findall('./MedlineCitation/Article/AuthorList/Author', article_element)
        if len(authors) > 0:
            author_names = []
            for author in authors:
                first_name = author.find('ForeName').text if author.find('ForeName') is not None else ""
                last_name = author.find('LastName').text if author.find('LastName') is not None else ""
                author_names.append(f"{first_name} {last_name}")
            author = author_names[0]

    if article_element.find('./MedlineCitation/Article/AuthorList/Author/AffiliationInfo/Affiliation') is not None:
        affiliation = [affiliation.text for affiliation in
                       article_element.find('./MedlineCitation/Article/AuthorList/Author', article_element).findall(
                           'AffiliationInfo/Affiliation')]

    if article_element.find('./MedlineCitation/Article/ArticleDate') is not None:
        year_element = article_element.find('./MedlineCitation/Article/ArticleDate/Year')
        month_element = article_element.find('./MedlineCitation/Article/ArticleDate/Month')
        day_element = article_element.find('./MedlineCitation/Article/ArticleDate/Day')

        year = int(year_element.text) if year_element is not None else None
        month = int(month_element.text) if month_element is not None else None
        day = int(day_element.text) if day_element is not None else None

        if year is not None and month is not None and day is not None:
            article_date = datetime.date(year, month, day)
            formatted_date = article_date.strftime('%Y-%m-%d')
        else:
            formatted_date = "Unknown"

    if article_element.find('./MedlineCitation/Article/PublicationTypeList') is not None:
        publication_type = [ptype.text for ptype in article_element.findall('.//PublicationType')]

    if article_element.find('./MedlineCitation/Article/Journal/Title') is not None:
        journal_title = article_element.find('./MedlineCitation/Article/Journal/Title').text

    if article_element.find('./MedlineCitation/KeywordList') is not None:
        keywords = [keyword.text for keyword in article_element.findall('.//Keyword')]

    # Create the dictionary
    article_dict = {
        "id": id,
        "title": title,
        "abstract": abstract,
        "url": url,
        "author": author,
        "affiliation": affiliation,
        "article_date": formatted_date,
        "publication_type": publication_type,
        "journal_title": journal_title,
        "keywords": keywords
    }
    return article_dict