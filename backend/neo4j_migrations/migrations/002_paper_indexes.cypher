// Create indexes for frequently searched properties
CREATE INDEX paper_doi IF NOT EXISTS FOR (p:Paper) ON (p.doi);
CREATE INDEX paper_arxiv_id IF NOT EXISTS FOR (p:Paper) ON (p.arxiv_id);
CREATE INDEX paper_semantic_scholar_id IF NOT EXISTS FOR (p:Paper) ON (p.semantic_scholar_id);
CREATE INDEX paper_title IF NOT EXISTS FOR (p:Paper) ON (p.title);
CREATE INDEX paper_year IF NOT EXISTS FOR (p:Paper) ON (p.publication_year);

CREATE INDEX author_name IF NOT EXISTS FOR (a:Author) ON (a.name);
CREATE INDEX method_name IF NOT EXISTS FOR (m:Method) ON (m.name);
CREATE INDEX dataset_name IF NOT EXISTS FOR (d:Dataset) ON (d.name);
CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name);
