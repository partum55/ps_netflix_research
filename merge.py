import csv

BASICS = "title.basics.tsv"
RATINGS = "title.ratings.tsv"
OUT = "IMDb.csv"


def load_ratings(path):
    print("loading ratings...")
    ratings = {}
    # Assumes the file has a header with fields including 'tconst', 'averageRating', 'numVotes'
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            tconst = row.get('tconst')
            if not tconst:
                # skip malformed rows
                continue
            ratings[tconst] = {
                'averageRating': row.get('averageRating', ''),
                'numVotes': row.get('numVotes', '')
            }
    print(f"loaded {len(ratings)} ratings")
    return ratings


def merge(basics_path, ratings_map, out_path):
    print("merging basics with ratings by tconst...")
    total = 0
    missing = 0
    # Assumes basics file has header with 'tconst', 'primaryTitle' and 'genres'
    with open(basics_path, newline='', encoding='utf-8') as fin, open(out_path, 'w', newline='', encoding='utf-8') as fout:
        reader = csv.DictReader(fin, delimiter='\t')
        writer = csv.writer(fout)
        writer.writerow(["tconst", "title", "genres", "averageRating", "numVotes"])  # header

        for row in reader:
            total += 1
            tconst = row.get('tconst', '')
            # try common title fields used in IMDb datasets
            title = row.get('primaryTitle') or row.get('originalTitle') or row.get('title') or ''
            genres = row.get('genres', '')

            rating = ratings_map.get(tconst)
            if rating:
                avg = rating.get('averageRating', '')
                votes = rating.get('numVotes', '')
            else:
                avg = ''
                votes = ''
                missing += 1

            writer.writerow([tconst, title, genres, avg, votes])

    print(f"done. total rows: {total}, missing ratings: {missing}")


if __name__ == '__main__':
    merge(BASICS, load_ratings(RATINGS), OUT)
