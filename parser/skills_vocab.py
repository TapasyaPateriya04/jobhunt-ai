"""Skill vocabulary and extraction shared by the resume parser and the JD analyzer.

Each canonical skill maps to the aliases that should be recognized in free text.
Matching is word-boundary safe for tokens with symbols (C++, C#, Node.js, .NET,
CI/CD) and case-insensitive except for short/ambiguous aliases (see
``_CASE_SENSITIVE``), which must appear with their canonical casing.
"""
from __future__ import annotations

import re
from functools import lru_cache

# canonical -> aliases (the canonical name itself is always an alias)
SKILLS: dict[str, tuple[str, ...]] = {
    # --- Programming languages ---
    "Python": ("Python", "Python3", "Python 3"),
    "Java": ("Java",),
    "JavaScript": ("JavaScript", "Javascript", "JS", "ES6", "ECMAScript"),
    "TypeScript": ("TypeScript", "TS"),
    "C": ("C",),
    "C++": ("C++", "cpp"),
    "C#": ("C#", "CSharp", "C Sharp"),
    "Go": ("Go", "Golang"),
    "Rust": ("Rust",),
    "Ruby": ("Ruby",),
    "PHP": ("PHP",),
    "Kotlin": ("Kotlin",),
    "Swift": ("Swift",),
    "Objective-C": ("Objective-C", "ObjC"),
    "Scala": ("Scala",),
    "R": ("R",),
    "MATLAB": ("MATLAB",),
    "Perl": ("Perl",),
    "Dart": ("Dart",),
    "Elixir": ("Elixir",),
    "Erlang": ("Erlang",),
    "Haskell": ("Haskell",),
    "Clojure": ("Clojure",),
    "Lua": ("Lua",),
    "Julia": ("Julia",),
    "Bash": ("Bash", "Shell scripting", "Shell Script", "Zsh"),
    "PowerShell": ("PowerShell",),
    "SQL": ("SQL",),
    "HTML": ("HTML", "HTML5"),
    "CSS": ("CSS", "CSS3"),
    "Sass": ("Sass", "SCSS"),
    "Solidity": ("Solidity",),
    "Verilog": ("Verilog", "SystemVerilog"),
    "VHDL": ("VHDL",),
    "Assembly": ("Assembly", "x86 Assembly"),
    "Fortran": ("Fortran",),
    "COBOL": ("COBOL",),
    "GraphQL": ("GraphQL",),
    # --- Web / backend frameworks ---
    "React": ("React", "React.js", "ReactJS"),
    "React Native": ("React Native",),
    "Next.js": ("Next.js", "NextJS"),
    "Angular": ("Angular", "AngularJS", "Angular.js"),
    "Vue.js": ("Vue", "Vue.js", "VueJS"),
    "Nuxt.js": ("Nuxt", "Nuxt.js"),
    "Svelte": ("Svelte", "SvelteKit"),
    "jQuery": ("jQuery",),
    "Redux": ("Redux",),
    "Tailwind CSS": ("Tailwind", "Tailwind CSS", "TailwindCSS"),
    "Bootstrap": ("Bootstrap",),
    "Node.js": ("Node.js", "NodeJS", "Node"),
    "Express.js": ("Express.js", "ExpressJS"),
    "NestJS": ("NestJS", "Nest.js"),
    "Deno": ("Deno",),
    "Django": ("Django",),
    "Django REST Framework": ("Django REST Framework", "DRF"),
    "Flask": ("Flask",),
    "FastAPI": ("FastAPI",),
    "Celery": ("Celery",),
    "SQLAlchemy": ("SQLAlchemy",),
    "Spring Boot": ("Spring Boot", "Spring Framework", "Spring MVC", "SpringBoot"),
    "Hibernate": ("Hibernate",),
    "Ruby on Rails": ("Ruby on Rails", "Rails", "RoR"),
    "Laravel": ("Laravel",),
    "Symfony": ("Symfony",),
    ".NET": (".NET", "dotnet", ".NET Core", "ASP.NET", "ASP.NET Core"),
    "Flutter": ("Flutter",),
    "Android": ("Android",),
    "iOS": ("iOS",),
    "SwiftUI": ("SwiftUI",),
    "Electron": ("Electron",),
    "gRPC": ("gRPC",),
    "REST APIs": ("REST", "RESTful", "REST API", "REST APIs", "RESTful APIs"),
    "Microservices": ("Microservices", "Microservice", "micro-services"),
    "WebSockets": ("WebSocket", "WebSockets"),
    "OAuth": ("OAuth", "OAuth2", "OAuth 2.0"),
    # --- Databases / storage ---
    "PostgreSQL": ("PostgreSQL", "Postgres", "Postgres SQL"),
    "MySQL": ("MySQL",),
    "MariaDB": ("MariaDB",),
    "SQLite": ("SQLite",),
    "Microsoft SQL Server": ("SQL Server", "MSSQL", "MS SQL", "T-SQL"),
    "Oracle": ("Oracle", "Oracle DB", "PL/SQL"),
    "MongoDB": ("MongoDB", "Mongo"),
    "Redis": ("Redis",),
    "Cassandra": ("Cassandra",),
    "DynamoDB": ("DynamoDB",),
    "Elasticsearch": ("Elasticsearch", "Elastic Search", "OpenSearch"),
    "Neo4j": ("Neo4j",),
    "Firebase": ("Firebase", "Firestore"),
    "Supabase": ("Supabase",),
    "Snowflake": ("Snowflake",),
    "BigQuery": ("BigQuery",),
    "Redshift": ("Redshift",),
    "ClickHouse": ("ClickHouse",),
    "Pinecone": ("Pinecone",),
    "NoSQL": ("NoSQL",),
    # --- Cloud / DevOps ---
    "AWS": ("AWS", "Amazon Web Services"),
    "AWS Lambda": ("Lambda", "AWS Lambda"),
    "Amazon S3": ("S3", "Amazon S3"),
    "Amazon EC2": ("EC2",),
    "Azure": ("Azure", "Microsoft Azure"),
    "GCP": ("GCP", "Google Cloud", "Google Cloud Platform"),
    "Heroku": ("Heroku",),
    "Vercel": ("Vercel",),
    "Netlify": ("Netlify",),
    "DigitalOcean": ("DigitalOcean",),
    "Cloudflare": ("Cloudflare",),
    "Docker": ("Docker", "Docker Compose"),
    "Kubernetes": ("Kubernetes", "K8s"),
    "Helm": ("Helm",),
    "OpenShift": ("OpenShift",),
    "Terraform": ("Terraform",),
    "Pulumi": ("Pulumi",),
    "CloudFormation": ("CloudFormation",),
    "Ansible": ("Ansible",),
    "Chef": ("Chef",),
    "Puppet": ("Puppet",),
    "Jenkins": ("Jenkins",),
    "GitHub Actions": ("GitHub Actions",),
    "GitLab CI": ("GitLab CI", "GitLab CI/CD"),
    "CircleCI": ("CircleCI",),
    "Travis CI": ("Travis CI",),
    "Argo CD": ("ArgoCD", "Argo CD"),
    "CI/CD": ("CI/CD", "CICD", "Continuous Integration", "Continuous Deployment"),
    "Git": ("Git",),
    "GitHub": ("GitHub",),
    "GitLab": ("GitLab",),
    "Bitbucket": ("Bitbucket",),
    "Linux": ("Linux", "Ubuntu", "Debian", "CentOS", "RHEL"),
    "Nginx": ("Nginx",),
    "Apache HTTP Server": ("Apache HTTP", "httpd"),
    "Prometheus": ("Prometheus",),
    "Grafana": ("Grafana",),
    "Datadog": ("Datadog",),
    "ELK Stack": ("ELK", "ELK Stack", "Kibana", "Logstash"),
    "Serverless": ("Serverless",),
    "DevOps": ("DevOps",),
    "SRE": ("SRE", "Site Reliability Engineering"),
    # --- Messaging / big data ---
    "Kafka": ("Kafka", "Apache Kafka"),
    "RabbitMQ": ("RabbitMQ",),
    "Apache Spark": ("Spark", "Apache Spark", "PySpark", "Spark SQL"),
    "Hadoop": ("Hadoop", "HDFS", "MapReduce"),
    "Hive": ("Hive", "Apache Hive"),
    "Apache Flink": ("Flink", "Apache Flink"),
    "Apache Airflow": ("Airflow", "Apache Airflow"),
    "dbt": ("dbt",),
    "Databricks": ("Databricks",),
    "ETL": ("ETL", "ELT"),
    "Data Warehousing": ("Data Warehouse", "Data Warehousing"),
    # --- Data science / ML ---
    "Machine Learning": ("Machine Learning", "ML"),
    "Deep Learning": ("Deep Learning", "DL"),
    "NLP": ("NLP", "Natural Language Processing"),
    "Computer Vision": ("Computer Vision", "CV"),
    "Generative AI": ("Generative AI", "GenAI", "Gen AI"),
    "LLMs": ("LLM", "LLMs", "Large Language Models", "Large Language Model"),
    "RAG": ("RAG", "Retrieval Augmented Generation", "Retrieval-Augmented Generation"),
    "Prompt Engineering": ("Prompt Engineering",),
    "AI": ("AI", "Artificial Intelligence"),
    "Reinforcement Learning": ("Reinforcement Learning",),
    "MLOps": ("MLOps",),
    "Data Science": ("Data Science",),
    "Data Analysis": ("Data Analysis", "Data Analytics"),
    "Statistics": ("Statistics", "Statistical Modeling", "Statistical Analysis"),
    "A/B Testing": ("A/B Testing", "A/B Tests", "AB Testing"),
    "TensorFlow": ("TensorFlow", "TF2"),
    "Keras": ("Keras",),
    "PyTorch": ("PyTorch", "Torch"),
    "JAX": ("JAX",),
    "scikit-learn": ("scikit-learn", "sklearn", "scikit learn"),
    "XGBoost": ("XGBoost",),
    "LightGBM": ("LightGBM",),
    "Pandas": ("Pandas",),
    "NumPy": ("NumPy",),
    "SciPy": ("SciPy",),
    "Matplotlib": ("Matplotlib",),
    "Seaborn": ("Seaborn",),
    "Plotly": ("Plotly",),
    "Jupyter": ("Jupyter", "Jupyter Notebook", "JupyterLab"),
    "OpenCV": ("OpenCV",),
    "spaCy": ("spaCy",),
    "NLTK": ("NLTK",),
    "Hugging Face": ("Hugging Face", "HuggingFace", "Transformers"),
    "LangChain": ("LangChain",),
    "LlamaIndex": ("LlamaIndex",),
    "OpenAI API": ("OpenAI", "OpenAI API"),
    "MLflow": ("MLflow",),
    "Kubeflow": ("Kubeflow",),
    "SageMaker": ("SageMaker",),
    "Vertex AI": ("Vertex AI",),
    "Tableau": ("Tableau",),
    "Power BI": ("Power BI", "PowerBI"),
    "Looker": ("Looker",),
    "Excel": ("Excel", "MS Excel", "Microsoft Excel"),
    "Streamlit": ("Streamlit",),
    # --- Testing / quality ---
    "pytest": ("pytest", "PyTest"),
    "unittest": ("unittest",),
    "JUnit": ("JUnit",),
    "Jest": ("Jest",),
    "Mocha": ("Mocha",),
    "Cypress": ("Cypress",),
    "Selenium": ("Selenium",),
    "Playwright": ("Playwright",),
    "Postman": ("Postman",),
    "TDD": ("TDD", "Test-Driven Development", "Test Driven Development"),
    "Unit Testing": ("Unit Testing", "Unit Tests"),
    # --- Tools / practices ---
    "Webpack": ("Webpack",),
    "Vite": ("Vite",),
    "Babel": ("Babel",),
    "npm": ("npm",),
    "Yarn": ("Yarn",),
    "Maven": ("Maven",),
    "Gradle": ("Gradle",),
    "Jira": ("Jira",),
    "Confluence": ("Confluence",),
    "Figma": ("Figma",),
    "Agile": ("Agile",),
    "Scrum": ("Scrum",),
    "Kanban": ("Kanban",),
    "OOP": ("OOP", "Object-Oriented Programming", "Object Oriented Programming"),
    "Data Structures": ("Data Structures",),
    "Algorithms": ("Algorithms",),
    "System Design": ("System Design", "Distributed Systems"),
    "Design Patterns": ("Design Patterns",),
    "Web Scraping": ("Web Scraping", "BeautifulSoup", "BeautifulSoup4", "Scrapy"),
    "Blockchain": ("Blockchain",),
    "Cybersecurity": ("Cybersecurity", "Information Security", "InfoSec"),
    "Networking": ("TCP/IP", "Networking"),
    "Embedded Systems": ("Embedded Systems", "Embedded C", "RTOS"),
    "Unity": ("Unity", "Unity3D"),
    "Unreal Engine": ("Unreal Engine", "Unreal"),
    # --- Added from real postings and a real resume (2026-09) ---
    "Spring Framework": ("Spring Framework", "Spring MVC", "Spring Security", "Spring Cloud",
                         "Spring Data", "Springboot"),
    "JPA": ("JPA", "Hibernate ORM"),
    "Mockito": ("Mockito",),
    "Multithreading": ("Multithreading", "Multi-threading", "Concurrency"),
    "JWT": ("JWT", "JSON Web Token", "JSON Web Tokens"),
    "RBAC": ("RBAC", "Role-Based Access Control", "Role Based Access Control"),
    "SSO": ("SSO", "Single Sign-On", "SAML"),
    "OpenAPI": ("OpenAPI", "Swagger"),
    "HTTP": ("HTTP", "HTTPS", "HTTP Protocols"),
    "Code Review": ("Code Review", "Code Reviews"),
    "Debugging": ("Debugging",),
    "QA": ("QA", "Quality Assurance"),
    "Web Accessibility": ("Web Accessibility", "WCAG", "a11y", "Accessibility Standards"),
    "UI/UX": ("UI/UX", "UX/UI"),
    "SaaS": ("SaaS",),
    "SDK": ("SDK", "SDKs"),
    "Observability": ("Observability",),
    "Infrastructure as Code": ("Infrastructure as Code", "IaC"),
    "Event-Driven Architecture": ("Event-Driven Architecture", "Event-driven", "Event Driven"),
    "Data Pipelines": ("Data Pipelines", "Data Pipeline"),
    "MCP": ("MCP", "Model Context Protocol"),
    "LangGraph": ("LangGraph",),
    "Fine-tuning": ("Fine-tuning", "Finetuning", "Fine tuning"),
    "Embeddings": ("Embeddings",),
    "Vector Databases": ("Vector Databases", "Vector Database", "Vector DB", "pgvector", "Pinecone"),
    "GPU": ("GPU", "GPUs", "CUDA"),
    "SAP": ("SAP", "ABAP"),
    "Salesforce": ("Salesforce",),
    "Shopify": ("Shopify",),
    "Stripe": ("Stripe",),
    "ERP": ("ERP",),
    "CRM": ("CRM",),
    "Mainframe": ("Mainframe", "z/OS", "COBOL"),
    "GDPR": ("GDPR",),
    "DBMS": ("DBMS", "RDBMS"),
    "Operating Systems": ("Operating Systems",),
    "Computer Networks": ("Computer Networks", "Computer Networking"),
    "VS Code": ("VS Code", "VSCode", "Visual Studio Code"),
    "IntelliJ IDEA": ("IntelliJ IDEA", "IntelliJ"),
}

# Aliases that must match with exact casing (short or ambiguous words).
_CASE_SENSITIVE: set[str] = {
    "C", "R", "Go", "JS", "TS", "ML", "DL", "CV", "AI", "Rust", "Swift", "Dart", "Julia",
    "Chef", "Puppet", "Unity", "Unreal", "Spark", "Hive", "Lambda", "Node", "Transformers",
    "Torch", "Oracle", "Excel", "Agile", "Algorithms", "Networking", "Serverless", "REST",
    "Helm", "Looker", "Vite", "Jest", "Mocha", "Electron", "Redux", "Flutter", "Scala",
    "Julia", "Assembly", "Statistics", "Rails", "RoR", "RAG", "Yarn", "Babel", "Deno",
    "Celery", "Mongo", "Flink", "Airflow", "Kafka", "Cassandra", "Bootstrap", "Kanban",
    "Scrum", "Snowflake", "Tableau", "Figma", "Unit Tests", "Bash", "Lua", "Perl", "Ruby",
    "Java", "Angular", "Vue", "Nuxt", "Svelte", "Git", "Linux", "Android", "Postman",
    "Cypress", "Selenium", "Maven", "Gradle", "Keras", "Pandas", "Seaborn",
    "QA", "SAP", "ERP", "CRM", "MCP", "SSO", "SDK", "SDKs", "GPU", "GPUs", "HTTP", "HTTPS", "JPA",
    "SAML", "Stripe", "Swagger", "Embeddings", "Debugging", "Observability",
    "Mainframe", "Concurrency",
}
# These are only case-sensitive because they are common English words; tech names
# like "Pandas"/"Git" are frequently written lowercase, so allow lowercase too.
_ALLOW_LOWER: set[str] = {
    "Git", "Linux", "Pandas", "Keras", "Seaborn", "Java", "Ruby", "Perl", "Lua", "Bash",
    "Angular", "Vue", "Svelte", "Kafka", "Airflow", "Celery", "Maven", "Gradle", "Scala",
    "Selenium", "Cypress", "Postman", "Tableau", "Figma", "Kanban", "Scrum", "Rust",
    "Redux", "Flutter", "Jest", "Deno", "Vite", "Android", "Cassandra", "Snowflake",
}

# Characters that may not touch a match on either side.
_LEFT = r"(?<![A-Za-z0-9_+#.\-/])"
_RIGHT = r"(?![A-Za-z0-9_+#]|\.[A-Za-z0-9]|-[A-Za-z0-9]|/[A-Za-z0-9])"


def _pattern(aliases: list[str], flags: int) -> re.Pattern | None:
    if not aliases:
        return None
    alts = sorted(set(aliases), key=len, reverse=True)
    body = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in alts)
    return re.compile(f"{_LEFT}(?:{body}){_RIGHT}", flags)


@lru_cache(maxsize=1)
def _compiled() -> tuple[re.Pattern | None, re.Pattern | None, dict[str, str], dict[str, str]]:
    ci_map: dict[str, str] = {}
    cs_map: dict[str, str] = {}
    for canonical, aliases in SKILLS.items():
        for alias in {canonical, *aliases}:
            if alias in _CASE_SENSITIVE:
                cs_map[alias] = canonical
                if alias in _ALLOW_LOWER:
                    cs_map[alias.lower()] = canonical
                    cs_map[alias.upper()] = canonical
            else:
                ci_map[alias.lower()] = canonical
    ci = _pattern(list(ci_map), re.IGNORECASE)
    cs = _pattern(list(cs_map), 0)
    return ci, cs, ci_map, cs_map


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def find_skills(text: str) -> list[str]:
    """Return canonical skills found in ``text``, ordered by first occurrence."""
    if not text:
        return []
    ci, cs, ci_map, cs_map = _compiled()
    hits: dict[str, int] = {}
    if ci is not None:
        for m in ci.finditer(text):
            canon = ci_map.get(_norm_ws(m.group(0)).lower())
            if canon and canon not in hits:
                hits[canon] = m.start()
    if cs is not None:
        for m in cs.finditer(text):
            canon = cs_map.get(_norm_ws(m.group(0)))
            if canon and (canon not in hits or m.start() < hits[canon]):
                hits[canon] = m.start()
    return [k for k, _ in sorted(hits.items(), key=lambda kv: kv[1])]


def canonicalize(skill: str) -> str | None:
    """Map an arbitrary skill string to its canonical name, if it's in the vocabulary."""
    found = find_skills(skill.strip())
    if len(found) == 1 and len(skill.strip()) <= 40:
        return found[0]
    return None
