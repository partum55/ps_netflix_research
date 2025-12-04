import argparse
import csv
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Dict, List, Set

IMDB_FILE = "IMDb.csv"
NETFLIX_FILE = "netflix_daily_top_10.csv"
OUTPUT_FILE = "netflix_with_imdb.csv"

def normalize_title(title):
    """Normalize title for better matching"""
    # Remove common suffixes and normalize
    title = title.lower().strip()
    # Remove ellipsis
    title = title.replace('…', '').replace('...', '')
    # Remove extra spaces
    title = ' '.join(title.split())
    return title


def tokenize_title(norm_title: str) -> List[str]:
    """Split normalized title into tokens for inverted-index lookup"""
    # split on spaces and punctuation, keep tokens >1 char
    tokens = [t for t in ''.join([(c if c.isalnum() else ' ') for c in norm_title]).split() if len(t) > 1]
    return tokens

def similarity_score(str1, str2):
    """Calculate similarity between two strings"""
    return SequenceMatcher(None, str1, str2).ratio()

def load_imdb_data(path):
    """Load IMDb data into a dictionary indexed by normalized title"""
    print("Loading IMDb data...")
    imdb_map: Dict[str, List[dict]] = {}
    # inverted index: token -> set of normalized titles
    token_idx: Dict[str, Set[str]] = defaultdict(set)
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row['title']
            normalized = normalize_title(title)
            
            # Store multiple entries with same normalized title
            if normalized not in imdb_map:
                imdb_map[normalized] = []

            # store numVotes as int when possible to speed comparisons
            num_votes = 0
            try:
                num_votes = int(row.get('numVotes') or 0)
            except (ValueError, TypeError):
                num_votes = 0

            entry = {
                'tconst': row['tconst'],
                'original_title': title,
                'genres': row.get('genres', ''),
                'averageRating': row.get('averageRating', ''),
                'numVotes': num_votes
            }

            imdb_map[normalized].append(entry)

            # update token index
            for tok in tokenize_title(normalized):
                token_idx[tok].add(normalized)
    
    print(f"Loaded {len(imdb_map)} unique normalized titles from IMDb")
    return imdb_map, token_idx

def find_best_match(netflix_title, imdb_map, token_idx=None, threshold=0.85, max_candidates=200, cache=None):
    """Find best matching IMDb entry for a Netflix title"""
    normalized_netflix = normalize_title(netflix_title)
    if cache is None:
        cache = {}
    # cached result
    if normalized_netflix in cache:
        return cache[normalized_netflix]
    
    # First try exact match
    if normalized_netflix in imdb_map:
        # Return the first match (or one with most votes if multiple)
        matches = imdb_map[normalized_netflix]
        if len(matches) == 1:
            cache[normalized_netflix] = matches[0]
            return matches[0]
        # Return the one with most votes
        best = max(matches, key=lambda x: x['numVotes'])
        cache[normalized_netflix] = best
        return best
    
    # Try fuzzy matching with token-index candidate reduction
    candidate_titles = set()

    if token_idx:
        for tok in tokenize_title(normalized_netflix):
            if tok in token_idx:
                candidate_titles.update(token_idx[tok])

    # fallback: if we have no candidates, consider a small subset (first N keys)
    if not candidate_titles:
        # take up to max_candidates normalized titles from imdb_map
        candidate_titles = set(list(imdb_map.keys())[:max_candidates])

    # limit candidates
    if len(candidate_titles) > max_candidates:
        # choose those with longest token overlap first: sort by common token count
        cand_list = list(candidate_titles)
        cand_list.sort(key=lambda t: -len(set(tokenize_title(t)).intersection(set(tokenize_title(normalized_netflix)))))
        cand_list = cand_list[:max_candidates]
    else:
        cand_list = list(candidate_titles)

    best_score = 0.0
    best_match = None
    for imdb_title_norm in cand_list:
        entries = imdb_map.get(imdb_title_norm)
        if not entries:
            continue
        score = similarity_score(normalized_netflix, imdb_title_norm)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = max(entries, key=lambda x: x['numVotes'])

    cache[normalized_netflix] = best_match
    return best_match

def merge_netflix_with_imdb(netflix_path, imdb_map, token_idx, output_path, threshold=0.85, max_candidates=200, use_fuzzy=True):
    """Merge Netflix data with IMDb ratings"""
    print("Merging Netflix data with IMDb...")
    
    total = 0
    matched = 0
    unmatched_titles = set()
    # cache for netflix title -> imdb match to avoid recomputing
    match_cache = {}
    
    with open(netflix_path, 'r', encoding='utf-8') as fin, \
         open(output_path, 'w', newline='', encoding='utf-8') as fout:
        
        reader = csv.DictReader(fin)
        
        # Create output header
        fieldnames = list(reader.fieldnames) + ['tconst', 'imdb_title', 'genres', 'averageRating', 'numVotes']
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in reader:
            total += 1
            netflix_title = row['Title']
            
            # Find matching IMDb entry
            imdb_match = None
            # exact and fuzzy matching via token index and cache
            if use_fuzzy:
                imdb_match = find_best_match(netflix_title, imdb_map, token_idx=token_idx, threshold=threshold, max_candidates=max_candidates, cache=match_cache)
            else:
                imdb_match = find_best_match(netflix_title, imdb_map, token_idx=None, threshold=1.0, max_candidates=0, cache=match_cache)
            
            if imdb_match:
                row['tconst'] = imdb_match['tconst']
                row['imdb_title'] = imdb_match['original_title']
                row['genres'] = imdb_match['genres']
                row['averageRating'] = imdb_match['averageRating']
                row['numVotes'] = str(imdb_match['numVotes'])
                matched += 1
            else:
                row['tconst'] = ''
                row['imdb_title'] = ''
                row['genres'] = ''
                row['averageRating'] = ''
                row['numVotes'] = ''
                unmatched_titles.add(netflix_title)
            
            writer.writerow(row)
            
            if total % 1000 == 0:
                print(f"Processed {total} rows, matched {matched}...")
    
    print("\nDone!")
    print(f"Total Netflix entries: {total}")
    print(f"Matched with IMDb: {matched} ({matched/total*100:.1f}%)")
    print(f"Unmatched: {len(unmatched_titles)}")
    
    if unmatched_titles and len(unmatched_titles) <= 20:
        print("\nUnmatched titles:")
        for title in sorted(unmatched_titles):
            print(f"  - {title}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Merge Netflix top 10 with IMDb data (optimized).')
    parser.add_argument('--imdb', default=IMDB_FILE, help='Path to IMDb CSV')
    parser.add_argument('--netflix', default=NETFLIX_FILE, help='Path to Netflix CSV')
    parser.add_argument('--output', default=OUTPUT_FILE, help='Output CSV path')
    parser.add_argument('--no-fuzzy', action='store_true', help='Disable fuzzy matching (exact only)')
    parser.add_argument('--threshold', type=float, default=0.85, help='Fuzzy matching threshold (0-1)')
    parser.add_argument('--max-candidates', type=int, default=200, help='Max fuzzy candidates to consider')
    args = parser.parse_args()

    imdb_data, token_index = load_imdb_data(args.imdb)
    merge_netflix_with_imdb(args.netflix, imdb_data, token_index, args.output, threshold=args.threshold, max_candidates=args.max_candidates, use_fuzzy=not args.no_fuzzy)

