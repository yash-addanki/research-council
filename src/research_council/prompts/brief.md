You are preparing a research brief for a council of AI models. Topic from the user's Notion queue:

Title: $title
Notes: $notes
Tags: $tags

If the notes are empty or the title is vague, infer the most useful reading and say which reading you chose in "question". Do not ask questions back.

Decide "kind": "build" if a good answer ends in choosing GitHub repos or tools and starting a project; otherwise "knowledge".

Reply with ONLY this JSON, no prose:
{"question": "...", "reading_chosen": "...", "success_criteria": ["..."], "kind": "build|knowledge",
 "angles": ["4 to 8 distinct web search queries"],
 "social_queries": ["3 to 6 short queries (2 to 5 words, no site names or words like reddit, x, hn, youtube, discussion); each is sent to every platform's own search"],
 "repo_queries": ["0 to 4 GitHub search queries; empty for knowledge topics"]}
