"""Rule-based skill extraction using an editable taxonomy (canonical name -> aliases).

Matching is case-insensitive with strict boundaries so that "java" does not match
"javascript", "sql" does not match "mysql" and "js" does not match "node.js".
Single-letter languages (C, R, Go) are only matched through unambiguous aliases
such as "golang" or "R programming" to avoid false positives.
"""
import re
from functools import lru_cache

TAXONOMY = {
    "Programming Languages": {
        "Python": ["python", "python3"],
        "Java": ["java"],
        "JavaScript": ["javascript", "js", "es6", "ecmascript"],
        "TypeScript": ["typescript"],
        "C++": ["c++", "cpp"],
        "C#": ["c#", "csharp"],
        "C": ["c programming", "c language"],
        "R": ["r programming", "r language", "rstudio"],
        "Go": ["golang"],
        "Rust": ["rust"],
        "PHP": ["php"],
        "Ruby": ["ruby"],
        "Kotlin": ["kotlin"],
        "Swift": ["swift"],
        "Scala": ["scala"],
        "MATLAB": ["matlab"],
        "Dart": ["dart"],
        "Bash": ["bash", "shell scripting", "shell script"],
    },
    "Web & Frameworks": {
        "Flask": ["flask"],
        "Django": ["django"],
        "FastAPI": ["fastapi"],
        "Spring Boot": ["spring boot", "springboot"],
        "Node.js": ["node.js", "nodejs", "node js"],
        "Express.js": ["express.js", "expressjs"],
        "React": ["react", "react.js", "reactjs"],
        "Angular": ["angular", "angularjs"],
        "Vue.js": ["vue.js", "vuejs", "vue"],
        "HTML": ["html", "html5"],
        "CSS": ["css", "css3"],
        "Bootstrap": ["bootstrap"],
        "Tailwind CSS": ["tailwind", "tailwind css", "tailwindcss"],
        "jQuery": ["jquery"],
        "REST API": ["rest api", "rest apis", "restful api", "restful apis", "restful", "rest services"],
        "GraphQL": ["graphql"],
        "Flutter": ["flutter"],
        "Android": ["android"],
        ".NET": [".net", "asp.net", "dotnet"],
    },
    "Databases & Data Engineering": {
        "SQL": ["sql", "t-sql", "pl/sql"],
        "MySQL": ["mysql"],
        "PostgreSQL": ["postgresql", "postgres"],
        "SQLite": ["sqlite", "sqlite3"],
        "MongoDB": ["mongodb", "mongo db"],
        "NoSQL": ["nosql"],
        "Redis": ["redis"],
        "SQL Server": ["sql server", "mssql", "ms sql"],
        "Oracle": ["oracle"],
        "Firebase": ["firebase"],
        "Elasticsearch": ["elasticsearch"],
        "Snowflake": ["snowflake"],
        "BigQuery": ["bigquery"],
        "Hadoop": ["hadoop"],
        "Spark": ["spark", "pyspark", "apache spark"],
        "Kafka": ["kafka"],
        "Airflow": ["airflow"],
        "ETL": ["etl", "elt"],
    },
    "Machine Learning & AI": {
        "Machine Learning": ["machine learning", "ml"],
        "Deep Learning": ["deep learning"],
        "Artificial Intelligence": ["artificial intelligence", "ai"],
        "NLP": ["nlp", "natural language processing"],
        "Computer Vision": ["computer vision"],
        "Scikit-learn": ["scikit-learn", "scikit learn", "sklearn"],
        "TensorFlow": ["tensorflow"],
        "Keras": ["keras"],
        "PyTorch": ["pytorch"],
        "XGBoost": ["xgboost"],
        "OpenCV": ["opencv"],
        "NLTK": ["nltk"],
        "spaCy": ["spacy"],
        "Hugging Face": ["hugging face", "huggingface"],
        "LLM": ["llm", "llms", "large language model", "large language models"],
        "Generative AI": ["generative ai", "genai"],
        "LangChain": ["langchain"],
        "Feature Engineering": ["feature engineering"],
        "Random Forest": ["random forest"],
        "Time Series": ["time series", "time-series", "forecasting"],
    },
    "Data Analysis & BI": {
        "Pandas": ["pandas"],
        "NumPy": ["numpy"],
        "Matplotlib": ["matplotlib"],
        "Seaborn": ["seaborn"],
        "Plotly": ["plotly"],
        "Power BI": ["power bi", "powerbi", "power-bi"],
        "Tableau": ["tableau"],
        "Excel": ["excel", "ms excel", "microsoft excel"],
        "Looker": ["looker", "looker studio", "data studio"],
        "DAX": ["dax"],
        "Power Query": ["power query"],
        "Data Analysis": ["data analysis", "data analytics"],
        "Data Visualization": ["data visualization", "data visualisation"],
        "Data Cleaning": ["data cleaning", "data wrangling", "data preprocessing", "data preparation"],
        "Statistics": ["statistics", "statistical analysis", "statistical modeling"],
        "EDA": ["eda", "exploratory data analysis"],
        "A/B Testing": ["a/b testing", "ab testing", "a/b test"],
        "Dashboards": ["dashboard", "dashboards"],
        "Business Intelligence": ["business intelligence"],
    },
    "Cloud & DevOps": {
        "AWS": ["aws", "amazon web services"],
        "Azure": ["azure"],
        "GCP": ["gcp", "google cloud"],
        "Docker": ["docker"],
        "Kubernetes": ["kubernetes", "k8s"],
        "CI/CD": ["ci/cd", "cicd", "ci cd"],
        "Jenkins": ["jenkins"],
        "GitHub Actions": ["github actions"],
        "Linux": ["linux"],
        "Terraform": ["terraform"],
    },
    "Tools & Practices": {
        "Git": ["git"],
        "GitHub": ["github"],
        "GitLab": ["gitlab"],
        "Jira": ["jira"],
        "Postman": ["postman"],
        "Jupyter": ["jupyter", "jupyter notebook"],
        "Streamlit": ["streamlit"],
        "Unit Testing": ["unit testing", "unit tests", "pytest", "unittest"],
        "Selenium": ["selenium"],
        "Agile": ["agile"],
        "Scrum": ["scrum"],
        "OOP": ["oop", "object-oriented programming", "object oriented programming"],
        "Data Structures": ["data structures", "dsa"],
        "Algorithms": ["algorithms"],
        "Microservices": ["microservices"],
        "JWT": ["jwt"],
        "WebSockets": ["websocket", "websockets", "socket.io"],
    },
}

# Closely related skills: used only to word recommendations ("your X transfers to Y").
RELATED = {
    "Django": ["Flask", "FastAPI"], "Flask": ["Django", "FastAPI"], "FastAPI": ["Flask", "Django"],
    "PostgreSQL": ["MySQL", "SQL", "SQLite"], "MySQL": ["PostgreSQL", "SQL", "SQLite"],
    "SQL": ["MySQL", "PostgreSQL", "SQLite", "SQL Server"], "Tableau": ["Power BI", "Looker"],
    "Power BI": ["Tableau", "Excel"], "PyTorch": ["TensorFlow", "Keras"],
    "TensorFlow": ["PyTorch", "Keras"], "Keras": ["TensorFlow", "PyTorch"],
    "Machine Learning": ["Scikit-learn", "Deep Learning"], "AWS": ["Azure", "GCP"],
    "Azure": ["AWS", "GCP"], "GCP": ["AWS", "Azure"], "React": ["Angular", "Vue.js"],
    "Angular": ["React", "Vue.js"], "MongoDB": ["NoSQL", "Redis"], "Docker": ["Kubernetes"],
    "Git": ["GitHub", "GitLab"], "REST API": ["Flask", "FastAPI", "Django", "Express.js"],
}

UNKNOWN_CATEGORY = "Other"

_ALIAS_TO_CANONICAL = {}
_CANONICAL_TO_CATEGORY = {}
for _category, _skills in TAXONOMY.items():
    for _canonical, _aliases in _skills.items():
        _CANONICAL_TO_CATEGORY[_canonical.lower()] = (_canonical, _category)
        _ALIAS_TO_CANONICAL[_canonical.lower()] = _canonical
        for _alias in _aliases:
            _ALIAS_TO_CANONICAL.setdefault(_alias.lower(), _canonical)


def _boundary_regex(term):
    """Case-insensitive regex that only matches `term` as a whole token."""
    parts = [re.escape(p) for p in re.split(r"\s+", term.strip()) if p]
    body = r"[\s\-]+".join(parts) if len(parts) > 1 else parts[0]
    return re.compile(r"(?<![A-Za-z0-9_+#.])" + body + r"(?![A-Za-z0-9_+#])", re.IGNORECASE)


@lru_cache(maxsize=1)
def _compiled_taxonomy():
    compiled = []
    for category, skills in TAXONOMY.items():
        for canonical, aliases in skills.items():
            terms = sorted({canonical.lower(), *[a.lower() for a in aliases]}, key=len, reverse=True)
            pattern = re.compile("|".join(_boundary_regex(t).pattern for t in terms), re.IGNORECASE)
            compiled.append((canonical, category, pattern))
    return compiled


def skill_category(name):
    entry = _CANONICAL_TO_CATEGORY.get((name or "").strip().lower())
    return entry[1] if entry else UNKNOWN_CATEGORY


def normalize_skill(term):
    """Map an alias to its canonical name; unknown skills keep the user's spelling."""
    cleaned = re.sub(r"\s+", " ", (term or "").strip()).strip(" .;:-")
    if not cleaned:
        return ""
    return _ALIAS_TO_CANONICAL.get(cleaned.lower(), cleaned)


def parse_skill_list(raw):
    """Split 'Python, Flask; SQL' (commas, semicolons, new lines, pipes) into canonical,
    de-duplicated skill names while preserving order."""
    if isinstance(raw, (list, tuple)):
        pieces = [str(p) for p in raw]
    else:
        pieces = re.split(r"[,;\n|•]+", raw or "")
    seen, result = set(), []
    for piece in pieces:
        name = normalize_skill(piece)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            result.append(name)
    return result


def extract_skills(text):
    """Return [{'name', 'category', 'count'}] for every taxonomy skill found, most mentioned first."""
    found = []
    if not text:
        return found
    for canonical, category, pattern in _compiled_taxonomy():
        count = len(pattern.findall(text))
        if count:
            found.append({"name": canonical, "category": category, "count": count})
    found.sort(key=lambda s: (-s["count"], s["name"]))
    return found


def skill_in_text(text, skill):
    """True if `skill` (canonical, alias, or custom term) appears in `text`."""
    if not text or not skill:
        return False
    canonical = normalize_skill(skill)
    for name, _category, pattern in _compiled_taxonomy():
        if name == canonical:
            return pattern.search(text) is not None
    return _boundary_regex(canonical).search(text) is not None
