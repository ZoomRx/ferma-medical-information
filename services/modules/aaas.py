import os
import json
import time
import requests

import marisa_trie


if __name__ == "__main__":
    import sys
    sys.path.append("./")
from config.es_settings import synonyms_bucket
from config.settings import creds


class Annotations:
    def __init__(self):
        self.headers = {
            "Authorization": "Bearer HL5NLBr2DspGLTDFNkPH8zrsasnPJMWvcB7AjTTg9mc3y",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.aaas_url = "https://aaas-web.ferma.ai/annotate"
        trie_folder_name = creds.agent_x_kg_context.trie_folder_name
        kg_terms_trie_name = creds.agent_x_kg_context.kg_terms_trie_name
        connections_trie_name = creds.agent_x_kg_context.connections_trie_name
        trie_files_path = "./services/modules/annotations/"

        if not os.path.exists(trie_files_path):
            os.mkdir(trie_files_path)

        synonyms_bucket.get_blob(
            trie_folder_name + kg_terms_trie_name
        ).download_to_filename(trie_files_path + kg_terms_trie_name)
        synonyms_bucket.get_blob(
            trie_folder_name + connections_trie_name
        ).download_to_filename(trie_files_path + connections_trie_name)

        terms_trie_filepath = trie_files_path + kg_terms_trie_name
        connections_trie_filepath = trie_files_path + connections_trie_name

        self.terms_trie = marisa_trie.BytesTrie()
        self.terms_trie.load(terms_trie_filepath)
        self.terms_trie = self.convert_trie_to_lowercase(self.terms_trie)

        self.conn_trie = marisa_trie.Trie()
        self.conn_trie.load(connections_trie_filepath)

    def convert_trie_to_lowercase(self, trie):
        """converts all elements in trie to lowercase for eliminating discrepancies 
            due to case of terms"""

        lowercase_keys = []
        lowercase_values = []

        for key, value in trie.items():
            lowercase_keys.append(key.lower().encode('utf-8').decode('unicode_escape'))
            lowercase_values.append(value)

        updated_trie = marisa_trie.BytesTrie(zip(lowercase_keys, lowercase_values))
        return updated_trie

    def get_annotations(self, text: str):
        """ returns annotations from input text """

        data = {
            "text": text, "sch_version": "V2"
        }
        response = requests.post(self.aaas_url, data, headers=self.headers)

        if response.status_code >= 200 and response.status_code < 300:
            return json.loads(response.content.decode("utf-8"))
        else:
            return {}

    def get_es_synonyms(self, q_terms: list, a_terms: list):
        """
        For given key terms of the question
        finds related words from answer/context data & question terms using KG
        considers both synonyms & hierarchies
        Example:
            Input:
                q_terms = ['oncology', 'cancer', 'non-hodgkin lymphoma']
                a_terms = ['hodgkin lymphoma', 'lymphoma']
            Output:
                {'oncology': ['hodgkin lymphoma', 'lymphoma', 'cancer', 'non-hodgkin lymphoma']}

        WorkFlow:
            q_terms = [a, b]
            a_terms = [p, q, r]

            1. Gets ids of terms (both ques & data) present in KG
                q_ids = [1, 2]
                a_ids = [21, 22, 23]
            2. Inter maps terms (cross product)
                cross product q_ids & a_ids
                cross product q_ids & q_ids
                cross_ids = [1:21, 1:22, 1:23, 2:21, 2:22, 2:23, 1:2, 2:1]
            3. Checks if mappings we have created in step2 is valid w.r.t KG
                connected_ids = [1:21, 1:23, 2:21, 1:2, 2:1]
                synonyms -  { 1 : [21, 23, 2],
                              2 : [1, 21]
                            }
            4. eliminates duplicates
                removes mapping of 2 as 2 is already mapped to 1
                synonyms - { 1 : [21, 23, 2] }

        """

        q_terms = [x.lower() for x in q_terms]
        a_terms = [x.lower() for x in a_terms]

        term_to_root_id_map = {}
        root_id_to_term_map = {}
        q_ids = []
        a_ids = []

        # Finds root_ids for terms and maps term to root_id & viceversa
        for term in set(q_terms).union(set(a_terms)):
            try:
                root_id = self.terms_trie[term][0].decode()
            except KeyError:
                continue

            term_to_root_id_map[term] = root_id
            if root_id in root_id_to_term_map:
                root_id_to_term_map[root_id].append(term)
            else:
                root_id_to_term_map[root_id] = [term]

            # adding root_id to both q_ids and a_ids to match the terms 
            # from both question and answer
            q_ids.append(root_id)
            a_ids.append(root_id)

        # cross_product of ques & data ids
        cross_ids = [str(x) + ":" + str(y) for x in q_ids for y in a_ids]
        # intra mapping of ques terms
        cross_ids.extend([str(x) + ":" + str(y) for x in q_ids for y in q_ids if x != y])
        # checks if connection between terms is present in KG
        connected_ids = []
        for ids in cross_ids:
            if ids in self.conn_trie:
                connected_ids.append(ids.split(":"))

        syns = {}
        for item in connected_ids:
            keys = root_id_to_term_map[(item[0].split(".")[0])]
            values = root_id_to_term_map[(item[1].split(".")[0])]

            if len(keys) > 1:
                syns[keys[0]] = [x for x in keys[1:] if x != keys[0]]

            if keys[0] in syns:
                syns[keys[0]].extend([x for x in values if x != keys[0]])

            else:
                syns[keys[0]] = [x for x in values if x != keys[0]]

        syns = {k: list(set(v)) for k, v in syns.items() if len(list(set(v)))}

        # eliminates duplicates
        popped_values = []
        for key, values in list(syns.items()):
            for value in values:
                if key not in popped_values:
                    syns.pop(value, None)
                    popped_values.append(value)

        return syns

    def main(self):
        q_terms = ['tepotinib']
        a_terms = ['cmet inhibitor']

        result = self.get_es_synonyms(q_terms, a_terms)
        return result


annotations = Annotations()

if __name__ == '__main__':
    start_time = time.time()
    annotations.main()
    print(f"Completed in {round(time.time() - start_time, 3)} secs")
