"""Generate clearly-labelled SYNTHETIC sample resumes (PDF + DOCX) and jobs.json.
All people are fictional; emails use example.com. Run: python scripts/generate_sample_data.py"""
import json
import sys
from pathlib import Path

import docx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "sample_data"
NOTE = "Synthetic sample resume - fictional person, generated for testing."

RESUMES = [
 ("Aarav Mehta", "pdf", "aarav.mehta@example.com", "+91 98100 11001", [
  ("SUMMARY", ["Backend developer building REST APIs with Python and Flask."]),
  ("SKILLS", ["Python, Flask, SQL, MySQL, REST API, Git, GitHub, Docker, Linux, Unit Testing, Agile"]),
  ("EXPERIENCE", ["Software Engineer, Nimbus Labs", "Jan 2021 - Present", "- Built REST APIs with Flask and MySQL serving 50k users", "- Containerised services with Docker and set up CI/CD", "Intern, Orbit Soft", "Jun 2020 - Dec 2020", "- Wrote unit tests with pytest"]),
  ("PROJECTS", ["Inventory Tracker", "- Flask + SQLite app with JWT authentication", "Chat Service", "- WebSockets and Redis"]),
  ("EDUCATION", ["B.Tech in Computer Science, Sample Institute of Technology, 2016 - 2020"]),
  ("CERTIFICATIONS", ["AWS Certified Cloud Practitioner"])]),
 ("Diya Sharma", "docx", "diya.sharma@example.com", "+91 98100 11002", [
  ("SUMMARY", ["Data scientist with a focus on machine learning and NLP."]),
  ("SKILLS", ["Python, Machine Learning, Deep Learning, NLP, Scikit-learn, TensorFlow, Pandas, NumPy, SQL, Jupyter, Git, Statistics"]),
  ("EXPERIENCE", ["Data Scientist, Quanta Analytics", "Mar 2019 - Present", "- Built churn prediction models with scikit-learn and XGBoost", "- Deployed NLP classifiers as REST API using Flask", "Data Analyst, Brightline", "Jul 2017 - Feb 2019", "- Cleaned data with Pandas and wrote SQL reports"]),
  ("PROJECTS", ["Resume Classifier", "- NLP pipeline using NLTK and TF-IDF", "Sales Forecasting", "- Time series forecasting with Python"]),
  ("EDUCATION", ["M.Tech in Data Science, Demo University, 2015 - 2017", "B.Tech in Information Technology, Demo College of Engineering, 2011 - 2015"]),
  ("CERTIFICATIONS", ["TensorFlow Developer Certificate", "Statistics for Data Science (online course)"])]),
 ("Kabir Singh", "pdf", "kabir.singh@example.com", "+91 98100 11003", [
  ("SUMMARY", ["Fresher data analyst skilled in SQL, Excel and Power BI dashboards."]),
  ("SKILLS", ["SQL, MySQL, Excel, Power BI, DAX, Python, Pandas, Data Visualization, Data Cleaning, Tableau"]),
  ("EXPERIENCE", ["Data Analyst Intern, Metro Retail", "Jun 2024 - Dec 2024", "- Built Power BI dashboards tracking weekly sales", "- Wrote MySQL queries for ad-hoc reporting"]),
  ("PROJECTS", ["Sales Analytics Dashboard", "- Excel, MySQL and Power BI end-to-end project", "Traffic Analysis", "- Python and Pandas EDA"]),
  ("EDUCATION", ["B.Tech in Data Science, Example Institute of Engineering, 2020 - 2024"]),
  ("CERTIFICATIONS", ["Microsoft Power BI Data Analyst (PL-300)"])]),
 ("Meera Iyer", "docx", "meera.iyer@example.com", "+91 98100 11004", [
  ("SUMMARY", ["Full-stack web developer working with React and Node.js."]),
  ("SKILLS", ["JavaScript, TypeScript, React, Node.js, Express.js, HTML, CSS, Tailwind CSS, MongoDB, REST API, Git, GitHub"]),
  ("EXPERIENCE", ["Frontend Developer, PixelWorks", "Aug 2022 - Present", "- Built React dashboards with TypeScript", "- Integrated REST APIs built on Node.js and MongoDB"]),
  ("PROJECTS", ["Job Board", "- MERN stack application", "Portfolio Site", "- React and Tailwind CSS"]),
  ("EDUCATION", ["B.E. in Computer Science, Sample College of Engineering, 2018 - 2022"]),
  ("CERTIFICATIONS", ["Meta Front-End Developer Certificate"])]),
 ("Rohan Verma", "pdf", "rohan.verma@example.com", "+91 98100 11005", [
  ("SUMMARY", ["Python developer with data engineering experience."]),
  ("SKILLS", ["Python, SQL, PostgreSQL, Airflow, ETL, Spark, Docker, AWS, Git, Linux, Pandas, REST API, FastAPI"]),
  ("EXPERIENCE", ["Data Engineer, CloudNest", "Feb 2020 - Present", "- Built ETL pipelines with Airflow and Spark", "- Exposed data services via FastAPI", "Python Developer, Greenfield Tech", "Jan 2018 - Jan 2020", "- Automated reports with Python and PostgreSQL"]),
  ("PROJECTS", ["Streaming Pipeline", "- Kafka and Spark processing"]),
  ("EDUCATION", ["B.Tech in Computer Science, Demo Technical University, 2014 - 2018"]),
  ("CERTIFICATIONS", ["AWS Solutions Architect Associate"])]),
 ("Sana Qureshi", "docx", "sana.qureshi@example.com", "+91 98100 11006", [
  ("SUMMARY", ["Graphic designer and brand strategist."]),
  ("SKILLS", ["Photoshop, Illustrator, Figma, Branding, Typography, Social Media Design, Video Editing"]),
  ("EXPERIENCE", ["Senior Designer, Studio Lumen", "Apr 2016 - Present", "- Led branding projects for retail clients", "- Created campaign visuals and packaging"]),
  ("EDUCATION", ["Bachelor of Fine Arts, Example Art College, 2012 - 2016"]),
  ("CERTIFICATIONS", ["Adobe Certified Professional"])]),
 ("Vikram Nair", "pdf", "vikram.nair@example.com", "+91 98100 11007", [
  ("SUMMARY", ["Recent graduate seeking a Python developer role."]),
  ("SKILLS", ["Python, Flask, SQL, SQLite, HTML, CSS, JavaScript, Git, Bootstrap"]),
  ("PROJECTS", ["Weather App", "- Flask app using an OpenWeather API", "Library Manager", "- Flask and SQLite CRUD application"]),
  ("EDUCATION", ["B.Tech in Computer Science, Sample University, 2021 - 2025"])]),
 ("Ishita Bose", "docx", "ishita.bose@example.com", "+91 98100 11008", [
  ("SUMMARY", ["Machine learning engineer with computer vision experience."]),
  ("SKILLS", ["Python, PyTorch, TensorFlow, Keras, OpenCV, Deep Learning, Computer Vision, Machine Learning, Docker, Git, Flask, REST API, NumPy"]),
  ("EXPERIENCE", ["ML Engineer, VisionAI Labs", "Sep 2021 - Present", "- Trained CNN models for defect detection using PyTorch", "- Served models through Flask REST API in Docker", "ML Intern, DeepScan", "Jan 2021 - Aug 2021", "- Image classification with Keras"]),
  ("PROJECTS", ["Deepfake Detector", "- CNN-based face-swap detection"]),
  ("EDUCATION", ["M.Sc. in Artificial Intelligence, Demo University, 2019 - 2021"]),
  ("CERTIFICATIONS", ["Deep Learning Specialization"])]),
]

JOBS = [
 {"title": "Python Developer", "description": "We are hiring a Python Developer to build and maintain backend services. You will design REST APIs with Flask, work with SQL databases, write unit tests and collaborate using Git. Exposure to machine learning is a plus.",
  "required_skills": ["Python", "Flask", "SQL", "Machine Learning", "REST API", "Git"], "min_experience_years": 2, "education_requirement": "Bachelor's degree in Computer Science or related field"},
 {"title": "Data Analyst", "description": "Join our analytics team to turn business data into insight. You will clean and analyse data, write SQL queries, build Power BI dashboards and present findings to stakeholders. Strong Excel and data visualization skills required.",
  "required_skills": ["SQL", "Excel", "Power BI", "Python", "Pandas", "Data Visualization"], "min_experience_years": 0, "education_requirement": "Bachelor's degree"},
 {"title": "Machine Learning Engineer", "description": "Looking for a Machine Learning Engineer to train, evaluate and deploy models. You will work with Python, TensorFlow or PyTorch, scikit-learn and NLP techniques, and ship models as REST APIs using Docker.",
  "required_skills": ["Python", "Machine Learning", "Deep Learning", "TensorFlow", "Scikit-learn", "NLP", "Docker"], "min_experience_years": 2, "education_requirement": "Bachelor's or Master's degree"},
 {"title": "Frontend Developer", "description": "Build responsive user interfaces with React and TypeScript. You will consume REST APIs, write clean HTML and CSS, and collaborate with designers and backend engineers using Git.",
  "required_skills": ["JavaScript", "TypeScript", "React", "HTML", "CSS", "REST API", "Git"], "min_experience_years": 1, "education_requirement": "Bachelor's degree"},
]


def build_pdf(path, name, email, phone, sections):
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(name.upper()), styles["Title"]), Paragraph(escape(f"{email} | {phone}"), styles["Normal"]), Spacer(1, 8)]
    for heading, lines in sections:
        story.append(Paragraph(f"<b>{heading}</b>", styles["Heading3"]))
        for line in lines:
            story.append(Paragraph(escape(line), styles["Normal"]))
    story += [Spacer(1, 14), Paragraph("<b>DECLARATION</b>", styles["Heading3"]), Paragraph(f"<i>{NOTE}</i>", styles["Italic"])]
    SimpleDocTemplate(str(path), pagesize=A4).build(story)


def build_docx(path, name, email, phone, sections):
    d = docx.Document()
    d.add_heading(name, 0)
    d.add_paragraph(f"{email} | {phone}")
    for heading, lines in sections:
        d.add_heading(heading, level=2)
        for line in lines:
            d.add_paragraph(line)
    d.add_heading("DECLARATION", level=2)
    d.add_paragraph(NOTE)
    d.save(str(path))


def main():
    (OUT / "resumes").mkdir(parents=True, exist_ok=True)
    for name, kind, email, phone, sections in RESUMES:
        path = OUT / "resumes" / (name.lower().replace(" ", "_") + "." + kind)
        (build_pdf if kind == "pdf" else build_docx)(path, name, email, phone, sections)
    (OUT / "jobs.json").write_text(json.dumps(JOBS, indent=2), encoding="utf-8")
    print(f"Wrote {len(RESUMES)} resumes and {len(JOBS)} jobs to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
