# -*- coding: utf-8 -*-
"""
Quality TF-IDF Embedder for NORSOK terminology
Significantly better than dummy embeddings for technical content
"""
import numpy as np
import pickle
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

class NorsokTFIDFEmbedder:
    """High-quality TF-IDF embedder optimized for NORSOK/technical content"""
    
    def __init__(self, dimension=384):
        self.dimension = dimension
        self.vectorizer = None
        self.is_trained = False
        
        # NORSOK-specific technical vocabulary
        self.norsok_vocabulary = [
            # Standards
            "NORSOK", "standard", "norm", "spesifikasjon", "krav",
            "M-001", "M-004", "M-501", "M-630", "M-650",
            
            # Materials & Welding  
            "sveising", "sveise", "sveiset", "sveiser", "sveiseprosess",
            "materiale", "stål", "legering", "karbon", "austentisk", "ferritisk",
            "korrosjon", "korrosjonsbeskyttelse", "galvanisk", "katodisk",
            
            # Technical terms
            "trykkprøving", "trykktesting", "trykkfall", "tetthetsprøving",
            "offshore", "subsea", "undervanns", "havbunn", "plattform",
            "sikkerhet", "risikovurdering", "HMS", "verneutstyr", "varmt_arbeid",
            
            # Properties
            "mekanisk", "egenskaper", "strekkfasthet", "flytegrense", "hardhet",
            "temperatur", "slitasje", "utmattelse", "sprøhet", "seighet",
            
            # Processes
            "produksjon", "installasjon", "vedlikehold", "inspeksjon",
            "kvalitetskontroll", "dokumentasjon", "sertifisering",
            
            # Components
            "rørledning", "ventil", "flanser", "bolter", "pakning",
            "pumpe", "kompressor", "separator", "manifold", "stigerør"
        ]
        
        # Technical stopwords (Norwegian + English)
        self.technical_stopwords = [
            "og", "eller", "i", "på", "av", "til", "for", "med", "den", "det", "som",
            "and", "or", "in", "on", "of", "to", "for", "with", "the", "that", "which",
            "skal", "må", "kan", "bør", "vil", "er", "var", "har", "ved", "under", "over"
        ]
        
    def _create_vectorizer(self):
        """Create optimized TF-IDF vectorizer for technical content"""
        return TfidfVectorizer(
            max_features=self.dimension,
            ngram_range=(1, 3),  # Include bigrams and trigrams
            lowercase=True,
            stop_words=self.technical_stopwords,
            token_pattern=r'\b[A-Za-z][A-Za-z0-9\-\_]*\b',  # Include technical terms with hyphens
            sublinear_tf=True,  # Better for technical docs
            min_df=1,  # Keep rare technical terms
            max_df=0.95,  # Remove too common words
            vocabulary=self._build_technical_vocabulary() if len(self.norsok_vocabulary) < self.dimension else None
        )
    
    def _build_technical_vocabulary(self):
        """Build comprehensive technical vocabulary"""
        vocabulary = self.norsok_vocabulary.copy()
        
        # Add variations and compounds
        base_terms = ["sveis", "korrosjon", "trykk", "materiale", "stål", "sikkerhet"]
        suffixes = ["ing", "er", "et", "ene", "ende", "prosess", "system", "krav"]
        
        for base in base_terms:
            for suffix in suffixes:
                vocabulary.append(base + suffix)
        
        # Add numbers and codes (common in standards)
        for i in range(1, 1000):
            vocabulary.extend([f"M-{i:03d}", f"NORSOK-{i}", f"NS-{i}"])
        
        return vocabulary[:self.dimension] if len(vocabulary) > self.dimension else vocabulary
    
    def train(self, training_texts=None):
        """Train the TF-IDF model on technical content"""
        if training_texts is None:
            # Default NORSOK-style training texts
            training_texts = [
                "NORSOK M-001 krever spesifikke sveiseprosedyrer for offshore konstruksjoner",
                "Korrosjonsbeskyttelse av stålkonstruksjoner i marint miljø",
                "Trykkprøving av rørledninger skal utføres i henhold til standardkrav",
                "Materialvalg for subsea utstyr må vurdere korrosjonsmotstand",
                "Sikkerhetstiltak ved varmt arbeid offshore inkluderer risikovurdering",
                "Kvalitetskontroll av sveiseskjøter ved ikke-destruktiv testing",
                "Mekaniske egenskaper av konstruksjonsstål for petroleumsindustri",
                "Installasjon og vedlikehold av subsea produksjonssystemer",
                "HMS-krav til personlig verneutstyr på offshore installasjoner",
                "Dokumentasjonskrav for sveiseprosedyrer etter NORSOK M-004"
            ]
        
        self.vectorizer = self._create_vectorizer()
        self.vectorizer.fit(training_texts)
        self.is_trained = True
        
        print(f"✅ TF-IDF model trained on {len(training_texts)} technical texts")
        print(f"   Vocabulary size: {len(self.vectorizer.vocabulary_)}")
        print(f"   Dimension: {self.dimension}")
    
    def embed(self, texts):
        """Generate embeddings for given texts"""
        if not self.is_trained:
            self.train()
        
        if isinstance(texts, str):
            texts = [texts]
        
        # Generate TF-IDF vectors
        tfidf_matrix = self.vectorizer.transform(texts)
        
        # Ensure exact dimension by padding or truncating
        embeddings = []
        for i in range(tfidf_matrix.shape[0]):
            vector = tfidf_matrix[i].toarray().flatten()
            
            if len(vector) < self.dimension:
                # Pad with zeros
                padded = np.zeros(self.dimension)
                padded[:len(vector)] = vector
                vector = padded
            elif len(vector) > self.dimension:
                # Truncate to exact dimension
                vector = vector[:self.dimension]
            
            embeddings.append(vector.tolist())
        
        return embeddings[0] if len(embeddings) == 1 else embeddings
    
    def similarity(self, text1, text2):
        """Calculate similarity between two texts"""
        emb1 = np.array(self.embed(text1)).reshape(1, -1)
        emb2 = np.array(self.embed(text2)).reshape(1, -1)
        return cosine_similarity(emb1, emb2)[0][0]
    
    def save_model(self, filepath):
        """Save trained model to file"""
        if not self.is_trained:
            raise ValueError("Model must be trained before saving")
        
        model_data = {
            'vectorizer': self.vectorizer,
            'dimension': self.dimension,
            'norsok_vocabulary': self.norsok_vocabulary,
            'is_trained': self.is_trained
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"✅ TF-IDF model saved to {filepath}")
    
    def load_model(self, filepath):
        """Load trained model from file"""
        if not os.path.exists(filepath):
            print(f"⚠️ Model file not found: {filepath}")
            return False
        
        try:
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)
            
            self.vectorizer = model_data['vectorizer']
            self.dimension = model_data['dimension']
            self.norsok_vocabulary = model_data['norsok_vocabulary']
            self.is_trained = model_data['is_trained']
            
            print(f"✅ TF-IDF model loaded from {filepath}")
            return True
        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            return False

def test_quality_embedder():
    """Test the quality of TF-IDF embedder"""
    print("🧪 Testing NORSOK TF-IDF Embedder Quality")
    print("=" * 50)
    
    embedder = NorsokTFIDFEmbedder()
    
    # Test cases for quality validation
    similarity_tests = [
        {
            "similar": ["NORSOK sveising krav", "Sveisekrav etter NORSOK"],
            "dissimilar": ["NORSOK sveising krav", "Pizza oppskrift"]
        },
        {
            "similar": ["Korrosjonsbeskyttelse offshore", "Offshore korrosjonsbeskyttelse"],
            "dissimilar": ["Korrosjonsbeskyttelse offshore", "Fotball resultater"]
        },
        {
            "similar": ["Trykkprøving rørledning", "Rørledning trykktest"],
            "dissimilar": ["Trykkprøving rørledning", "Katte videoer"]
        }
    ]
    
    total_tests = len(similarity_tests)
    passed_tests = 0
    
    for i, test in enumerate(similarity_tests):
        similar_sim = embedder.similarity(test["similar"][0], test["similar"][1])
        dissimilar_sim = embedder.similarity(test["dissimilar"][0], test["dissimilar"][1])
        
        print(f"Test {i+1}:")
        print(f"  Similar: {similar_sim:.3f} - '{test['similar'][0]}' vs '{test['similar'][1]}'")
        print(f"  Dissimilar: {dissimilar_sim:.3f} - '{test['dissimilar'][0]}' vs '{test['dissimilar'][1]}'")
        
        if similar_sim > dissimilar_sim:
            print(f"  ✅ PASS - Similar texts have higher similarity")
            passed_tests += 1
        else:
            print(f"  ❌ FAIL - Dissimilar texts have higher similarity")
        print()
    
    success_rate = passed_tests / total_tests * 100
    print(f"📊 Quality Test Results: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        print("✅ EXCELLENT: TF-IDF embedder shows good quality")
    elif success_rate >= 60:
        print("⚠️ ACCEPTABLE: TF-IDF embedder shows moderate quality")
    else:
        print("❌ POOR: TF-IDF embedder needs improvement")
    
    return success_rate >= 60

if __name__ == "__main__":
    test_quality_embedder() 