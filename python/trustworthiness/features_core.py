import multiprocessing
import sys
from datetime import date
import nltk
from bs4 import BeautifulSoup
from keras.preprocessing.sequence import pad_sequences
from sklearn.externals import joblib
from textstat.textstat import textstat
from sumy.parsers.html import HtmlParser
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
from singleton_decorator import singleton
from urllib.request import urlopen
from keras.datasets import imdb
from keras.models import load_model
from keras.preprocessing import sequence
import lxml.html
import json
import numpy as np
import socket
from multiprocessing.dummy import Pool
import pandas as pd
from tldextract import tldextract
from pathlib import Path
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from coffeeandnoodles.core.util import get_md5_from_string
from coffeeandnoodles.core.web.microsoft_azure.microsoft_azure_helper import MicrosoftAzurePlatform
from coffeeandnoodles.core.web.scrap.scrap import WebScrap
from config import DeFactoConfig
import whois
from urllib.parse import urlparse
import os
import warnings
from defacto.definitions import DEFACTO_LEXICON_GI_PATH, BENCHMARK_FILE_NAME_TEMPLATE, \
    DATASET_3C_SCORES_PATH, DATASET_3C_SITES_PATH, MAX_WEBSITES_PROCESS, SOCIAL_NETWORK_NAMES, \
    OUTPUT_FOLDER, TIMEOUT_MS, DATASET_MICROSOFT_PATH
from trustworthiness.util import get_html_file_path, get_features_web_microsoft, get_features_web_3c
from trustworthiness.topic_utils import TopicTerms

with warnings.catch_warnings():
    warnings.filterwarnings("ignore",category=FutureWarning)

__author__ = "Diego Esteves"
__copyright__ = "Copyright 2018, DeFacto Project"
__credits__ = ["Diego Esteves", "Aniketh Reddy", "Piyush Chawla"]
__license__ = "Apache"
__version__ = "0.0.1"
__maintainer__ = "Diego Esteves"
__email__ = "diegoesteves@gmail.com"
__status__ = "Dev"

config = DeFactoConfig()
bing = MicrosoftAzurePlatform(config.translation_secret)

class Singleton(object):
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = object.__new__(cls, *args, **kwargs)
        return cls._instance

@singleton
class GeneralInquirer:

    def __init__(self, path):
        config.logger.info('loading GI lexicon...')
        self.df = pd.read_table(path, sep="\t", na_values=0, low_memory=False, skiprows=1)
        self.df.drop(self.df.columns[[1, 184, 185]], axis=1, inplace=True)
        self.df.columns = ['col_' + str(i) for i in range(0,183)]
        self.df.fillna(0, inplace=True)
        self.df.set_index('col_0', inplace=True)
        self.tot_features = len(self.df.columns)
        config.logger.info('done! ' + str(self.tot_features) + ' word features')

    def get_word_vector(self, word):
        word = word.upper()
        not_found=[0] * self.tot_features
        try:
            ret = self.df.loc[word]
        except:
            try:
                ret = self.df.loc[word + '#1']
            except:
                return not_found
        return [1 if c != 0 else 0 for c in ret]

@singleton
class Classifiers():
    def __init__(self):
        config.logger.info('loading classifiers...')
        path_textclass = config.dir_models + 'textcategory/'
        self.clf_textclass_1 = joblib.load(path_textclass + 'clf_business_category_multinomialnb_tfidf.pkl')
        self.vec_textclass_1 = joblib.load(path_textclass + 'vec_business_category_multinomialnb_tfidf.pkl')
        self.clf_textclass_2 = joblib.load(path_textclass + 'clf_entertainment_category_multinomialnb_tfidf.pkl')
        self.vec_textclass_2 = joblib.load(path_textclass + 'vec_entertainment_category_multinomialnb_tfidf.pkl')
        self.clf_textclass_3 = joblib.load(path_textclass + 'clf_politics_category_multinomialnb_tfidf.pkl')
        self.vec_textclass_3 = joblib.load(path_textclass + 'vec_politics_category_multinomialnb_tfidf.pkl')
        self.clf_textclass_4 = joblib.load(path_textclass + 'clf_religion_category_multinomialnb_tfidf.pkl')
        self.vec_textclass_4 = joblib.load(path_textclass + 'vec_religion_category_multinomialnb_tfidf.pkl')
        self.clf_textclass_5 = joblib.load(path_textclass + 'clf_sports_category_multinomialnb_tfidf.pkl')
        self.vec_textclass_5 = joblib.load(path_textclass + 'vec_sports_category_multinomialnb_tfidf.pkl')
        self.clf_textclass_6 = joblib.load(path_textclass + 'clf_tech_category_multinomialnb_tfidf.pkl')
        self.vec_textclass_6 = joblib.load(path_textclass + 'vec_tech_category_multinomialnb_tfidf.pkl')

        path_spam = config.dir_models + '/spam/'
        self.clf_spam_1 = joblib.load(path_spam + 'clf_41_spam_onevsrestclassifier_tfidf.pkl')
        self.vec_spam_1 = joblib.load(path_spam + 'vec_41_spam_onevsrestclassifier_tfidf.pkl')

        path_sentiment = config.dir_models + '/sentimentanalysis/'
        self.clf_sentiment_1 = load_model(path_sentiment + 'imdb_1600')
        self.vec_sentiment_1 = imdb.get_word_index()
        config.logger.info('done')

@singleton
class OpenSourceData():
    def __init__(self):
        config.logger.info('loading open source data...')
        try:
            sources = '../data/datasets/opensources/sources.csv'
            sources = open(sources, "r").readlines()[1:]
            types = {}
            for source in sources:
                source = source.split(",")
                types[source[0]] = [source[1], source[2], source[3]]
            self.types = types
        except:
            raise

@singleton
class PageRankData():
    def __init__(self):
        path = OUTPUT_FOLDER + 'open_pagerank/'
        config.logger.info('loading page rank extracted data: ' + path)
        try:
            pgs=dict()
            for file in os.listdir(path):
                if file.endswith(".json"):
                    with open(path + file, 'r') as fh:
                        temp=json.load(fh)
                        if temp['status_code'] == 200:
                            for w in temp['response']:
                                if w['status_code'] == 200:
                                    pgs[w['domain']] = {'page_rank_decimal': float(w['page_rank_decimal']), 'rank': int(w['rank'])}
            self.pg = pgs
            config.logger.info('done')
        except Exception as e:
            config.logger.error(repr(e))
            raise e

class FeaturesCore:
    """The feature extractor for the trustworthiness module.

    It implements a set of feature extractors for a given web page.
    """

    def __init__(self, url, timeout=TIMEOUT_MS, local_file_path=None, error=False, save_webpage_file=False):
        #self.DataTable = pd.read_table(config.dataset_ext_microsoft_webcred_webpages_cache,sep=",",header=None,names=["topic","query","rank","url","rating"])
        try:
            assert (local_file_path is not None and save_webpage_file is False) or \
                   (local_file_path is None)
            self.url = url
            self.local_file_path = local_file_path
            self.timeout = timeout
            self.error = error
            self.webscrap = None
            self.title = None
            self.body = None
            clf = Classifiers()
            self.classifiers = clf
            self.topic = TopicTerms()
            self.sources = OpenSourceData()
            self.page_rank = PageRankData()
            self.gi = GeneralInquirer(DEFACTO_LEXICON_GI_PATH)
            self.error_message = ''
        except Exception as e:
            self.error_message = repr(e)
            self.error = True

    def get_final_feature_vector(self):
       try:
           out = []
           out.extend(self.get_feat_archive_tot_records(config.waybackmachine_weight, config.waybackmachine_tot))
           out.append(self.get_feat_domain())
           out.append(self.get_feat_suffix())
           out.append(self.get_feat_source_info())
           out.append(self.get_feat_tot_outbound_links(tp='http'))
           out.append(self.get_feat_tot_outbound_links(tp='https'))
           out.append(self.get_feat_tot_outbound_links(tp='ftp'))
           out.append(self.get_feat_tot_outbound_links(tp='ftps'))
           out.append(self.get_feat_tot_outbound_domains(tp='http'))
           out.append(self.get_feat_tot_outbound_domains(tp='https'))
           out.append(self.get_feat_tot_outbound_domains(tp='ftp'))
           out.append(self.get_feat_tot_outbound_domains(tp='ftps'))
           out.extend(self.get_feat_text_category(self.title))
           out.extend(self.get_feat_text_category(self.body))
           out.extend(self.get_feat_text_category(self.get_summary_lex_rank(100)))
           out.extend(self.get_feat_text_category(self.get_summary(100)))
           out.extend(self.get_feat_readability_metrics())
           out.extend(self.get_feat_spam(self.title))
           out.extend(self.get_feat_spam(self.body))
           out.extend(self.get_feat_social_media_tags())
           out.append(self.get_opensources_classification(self.url))
           out.extend(self.get_opensources_count(self.url))
           out.extend(self.get_open_page_rank(self.url))
           out.extend(self.get_gi(self.body))
           out.extend(self.get_gi(self.title))
           out.extend(self.get_vader_lexicon(self.body))
           out.extend(self.get_vader_lexicon(self.title))
           out.extend(self.get_whois_features(self.webscrap.get_domain()))


           return out

       except Exception as e:
           config.logger.error(repr(e))

    def rms(self,vec):
        vec = np.multiply(vec,vec)
        vec = np.sum(vec)
        return np.sqrt(vec)

    def distance(self,vec1,vec2):
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        prod = np.sum(np.multiply(vec1,vec2))
        return (prod*1.0)/(self.rms(vec1)*self.rms(vec2))

    def get_summary(self,num_sentence):
        out = ''
        try:
            try:
                parser = HtmlParser.from_url(self.url, Tokenizer("english"))
            except:
                try:
                    parser = PlaintextParser.from_string(self.body, Tokenizer("english"))
                except Exception as e:
                    raise(e)

            stemmer = Stemmer('english')
            summarizer = Summarizer(stemmer)
            summarizer.stop_words = get_stop_words('english')

            for sentence in summarizer(parser.document, num_sentence):
                out+=str(sentence)
        except:
            return self.body

        return out

    def get_summary_lex_rank(self,num_sentence):
        from sumy.parsers.plaintext import PlaintextParser  # other parsers available for HTML etc.
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.lex_rank import LexRankSummarizer  # We're choosing Lexrank, other algorithms are also built in

        try:
            parser = HtmlParser.from_url(self.url, Tokenizer("english"))
        except:
            try:
                parser = PlaintextParser.from_string(self.body, Tokenizer("english"))
            except Exception as e:
                raise(e)

        summarizer = LexRankSummarizer()
        summary = summarizer(parser.document, num_sentence)
        out=''
        for sentence in summary:
            out+= str(sentence)
        return out

    def get_feat_text_category(self, text):
        '''
        returns a vector of classes of (6) categories (0=yes,1=no) for an input text
        i.e., [0 0 0 0 0 0]
        '''
        try:
            if text is None or len(text.split()) == 0:
                return [0,0,0,0,0,0]
            else:
                aux = text.split()
                limit = min(len(aux), 1000)
                text = " ".join(aux[i] for i in range(0, limit-1))

                try:
                    if bing.bing_detect_language(text) != 'en':
                        text_en = bing.bing_translate_text(text, 'en')
                        text=text_en
                except Exception as e:
                    config.logger.error(repr(e))

                vec_text_1 = self.classifiers.vec_textclass_1.transform([text])
                vec_text_2 = self.classifiers.vec_textclass_2.transform([text])
                vec_text_3 = self.classifiers.vec_textclass_3.transform([text])
                vec_text_4 = self.classifiers.vec_textclass_4.transform([text])
                vec_text_5 = self.classifiers.vec_textclass_5.transform([text])
                vec_text_6 = self.classifiers.vec_textclass_6.transform([text])

                out = []
                out.append(round(self.classifiers.clf_textclass_1.predict_proba(vec_text_1)[0][1],3))
                out.append(round(self.classifiers.clf_textclass_2.predict_proba(vec_text_2)[0][1],3))
                out.append(round(self.classifiers.clf_textclass_3.predict_proba(vec_text_3)[0][1],3))
                out.append(round(self.classifiers.clf_textclass_4.predict_proba(vec_text_4)[0][1],3))
                out.append(round(self.classifiers.clf_textclass_5.predict_proba(vec_text_5)[0][1],3))
                out.append(round(self.classifiers.clf_textclass_6.predict_proba(vec_text_6)[0][1],3))

                return out
        except Exception as e:
            config.logger.error(repr(e))
            return [0,0,0,0,0,0]

    def get_feat_spam(self, text):
        '''
        returns the class distribution (SPAM/HAM) for an input text
        i.e., [[predicted ham prob, predicted spam prob], [predicted class]]
        '''
        try:
            if text is None or text == '':
                return 0, 0, 0

            vec_text = self.classifiers.vec_spam_1.transform([text])
            # attention here, if the classifiers supports probabilities, otherwise need to change to predict()
            pred_klass = 0 if self.classifiers.clf_spam_1.predict(vec_text)[0] == 'ham' else 1
            pred_probs = self.classifiers.clf_spam_1.predict_proba(vec_text)[0]
            return [pred_probs[0], pred_probs[1], pred_klass]
        except Exception as e:
            config.logger.error(repr(e))
            return 0, 0, 0

    def get_feat_sentiment(self):
        '''
        returns probability 0-1
        '''
        text = self.get_summary_lex_rank(200)
        top_words = 10000
        textList = []
        text = text.split(' ')
        for i in text:
            i = self.filterTerm(i)
            if i in self.classifiers.vec_sentiment_1:
                textList.append(self.classifiers.vec_sentiment_1[i])
            else:
                textList.append(0)

        max_review_length = 1600

        #if(len(textList)>max_review_length):
        #    textList = textList(:max_review_length)

        inputList = []
        textList = np.array(textList)
        inputList.append(textList)
        modelInput = sequence.pad_sequences(inputList,maxlen = max_review_length)

        return self.classifiers.clf_sentiment_1.predict(modelInput)

    def get_feat_domain(self):
        try:
            return self.webscrap.get_domain()
        except Exception as e:
            config.logger.error(repr(e))
            return ''

    def get_whois_features(self, domain):
        data = []
        _OK = 1
        _NONE = -1
        _ERR = -2
        try:
            try:
                details = whois.whois(domain)
                if isinstance(details.expiration_date, list) == True:
                    dt = details.expiration_date[0]
                else:
                    dt = details.expiration_date
                if isinstance(details.creation_date, list) == True:
                    dtc = details.creation_date[0]
                else:
                    dtc = details.creation_date
                if dt is None:
                    data.append(_NONE)
                else:
                    data.append((dt.date() - date.today()).days)
                if dtc is None:
                    data.append(_NONE)
                else:
                    data.append((date.today() - dtc.date()).days)
                data.append(_NONE if details.name_servers is None else len(details.name_servers))
                data.append(_NONE if details.emails is None else len(details.emails))
                data.append(_NONE if details.name is None else _OK)
                data.append(_NONE if details.address is None else _OK)
                data.append(_NONE if details.city is None else _OK)
                data.append(_NONE if details.state is None else _OK)
                data.append(_NONE if details.zipcode is None else _OK)
                data.append(_NONE if details.country is None else _OK)
            except:
                raise
        except Exception as e:
            data.append([_ERR] * 10)

        return data

    def get_feat_suffix(self):
        try:
            return self.webscrap.get_suffix()
        except Exception as e:
            config.logger.error(repr(e))
            return ''

    def get_feat_source_info(self):
        try:
            return self.webscrap.get_tot_occurences_authority()
        except Exception as e:
            config.logger.error(repr(e))
            return 0

    def get_feat_tot_outbound_links(self, tp):
        try:
            return len(self.webscrap.get_outbound_links(tp))
        except Exception as e:
            config.logger.error(repr(e))
            return 0

    def get_feat_tot_outbound_domains(self, tp):
        try:
            return len(self.webscrap.get_outbound_domains(tp))
        except Exception as e:
            config.logger.error(repr(e))
            return 0

    def get_feat_archive_tot_records(self, w, tot_records=None):
        '''
        returns basic statistics about cached data for a URL
        :param w: penalization factor for 404 URL (tries domain)
        :param tot_records: the max number of records to search (optional) and just for 'get_wayback_tot_via_api' calls
        :return:
        '''
        out=0
        last=None
        try:
            w=float(w)
            out, last =self.webscrap.get_wayback_tot_via_memento(w)
            if out == 0:
                out, last = self.webscrap.get_wayback_tot_via_memento(w, self.webscrap.get_full_domain())
        except Exception as e:
            config.logger.error(repr(e))

        return [out, 0 if last is None else last]

    def get_feat_readability_metrics(self):
        # https://github.com/shivam5992/textstat

        try:
            test_data = self.webscrap.get_body()
            out = []
            out.append(textstat.flesch_reading_ease(test_data))
            out.append(textstat.smog_index(test_data))
            out.append(textstat.flesch_kincaid_grade(test_data))
            out.append(textstat.coleman_liau_index(test_data))
            out.append(textstat.automated_readability_index(test_data))
            out.append(textstat.dale_chall_readability_score(test_data))
            out.append(textstat.difficult_words(test_data))
            out.append(textstat.linsear_write_formula(test_data))
            out.append(textstat.gunning_fog(test_data))
            #out.append(textstat.text_standard(test_data))
            return out
        except Exception as e:
            config.logger.error(repr(e))
            return [0] * 9

    def get_feat_social_media_tags(self):
        try:
            return self.webscrap.get_total_social_media_tags()
        except Exception as e:
            config.logger.error(repr(e))
            return [0] * SOCIAL_NETWORK_NAMES

    def get_opensources_classification(self, url):
        '''
        Function returns 0 if there is no information on the webpage in the OpenSources database, 1 if it is a reliable source and 2 if it is an unreliable source
        '''
        try:
            parsed_url = urlparse(url)
            hostname = str(parsed_url.hostname)
            if hostname.startswith('www'):
                hostname = hostname[4:]
            if hostname not in self.sources.types.keys():
                return 0  # no info on this page
            if "reliable" in self.sources.types[hostname]:
                return 1  # this is a reliable sourc
            else:
                return 2  # not a very reliable source
        except Exception as e:
            config.logger.error(repr(e))
            return 0

    def get_opensources_count(self, url):
        '''
        Function return the number of reliable sources, number of unreliable sources and the total number of sources referenced by a webpage in that order
        '''
        try:
            connection = urlopen(url, timeout=TIMEOUT_MS)
            dom = lxml.html.fromstring(connection.read())
            num_reliable = 0
            num_unreliable = 0
            total_num_sources = 0

            for link in dom.xpath('//a/@href'):  # select the url in href for all a tags(links)
                total_num_sources += 1
                hostname = str(urlparse(link).hostname)
                if hostname.startswith('www'):
                    hostname = hostname[4:]
                if hostname not in self.sources.types.keys():
                    continue  # no info on this lin
                elif "reliable" in self.sources.types[hostname]:
                    num_reliable += 1  # this is a reliable source
                else:
                    num_unreliable += 1  # not a very reliable source

            return [num_reliable, num_unreliable, total_num_sources]

        except Exception as e:
            config.logger.error(repr(e))
            return [0, 0, 0]

    def get_number_of_arguments(self, url):
        try:
            urlcode = get_md5_from_string(url)
            with open(config.root_dir_data + 'marseille/output.json', 'r') as fh:
                dargs = json.load(fh)
            try:
                tot_args=dargs[urlcode]
                return tot_args
            except KeyError:
                config.logger.warn('this should not happen but lets move on for now, check marseille dump files/pre-processing!')
                raise
        except Exception as e:
            config.logger.error(repr(e))
            raise

    def get_open_page_rank(self, url):
        try:
            o = tldextract.extract(url)
            domain=('%s.%s' % (o.domain, o.suffix))
            try:
                pginfo=self.page_rank.pg[domain]
            except KeyError:
                config.logger.warn('page rank information for domain [' + domain + '] not found')
                return [0, 0]
            return [pginfo['page_rank_decimal'], pginfo['rank']]
        except Exception as e:
            config.logger.error(repr(e))
            return [0, 0]

    def get_sequence_html(self):
        try:
            return self.webscrap.get_body_sequence_tags()
        except Exception as e:
            config.logger.error(repr(e))
            return ''

    def get_gi(self, text):

        try:
            vectors = []
            tokens = nltk.word_tokenize(text)
            for token in tokens:
                vectors.append(self.gi.get_word_vector(token))
            if len(vectors) == 0:
                return [0] * self.gi.tot_features
            else:
                return [sum(x) for x in zip(*vectors)]
        except Exception as e:
            config.logger.error(repr(e))
            return [0] * self.gi.tot_features

    def get_vader_lexicon(self, text):
        try:
            analyzer = SentimentIntensityAnalyzer()
            scores = analyzer.polarity_scores(text)
            return [scores.get('neg'), scores.get('neu'), scores.get('pos'), scores.get('compound')]
        except Exception as e:
            config.logger.error(repr(e))
            return [0, 0, 0, 0]

    def get_senti_wordnet_lexicon(word):
        from nltk.corpus import sentiwordnet as swn
        xxx = swn.senti_synsets(word)
        for s in xxx:
            print(s._neg_score)
            print(s._pos_score)
            print(s._obj_score)

    def call_web_scrap(self):
        try:
            self.webscrap = WebScrap(self.url, self.timeout, 'lxml', self.local_file_path)
            self.title = self.webscrap.get_title()
            self.body = self.webscrap.get_body()
        except Exception as e:
            self.error = True
            self.error_message = repr(e)
            config.logger.error(self.error_message)
