# Summarization Prompt

For each item, produce a short operational summary:

- 1 to 2 sentences
- Focus on what happened, why it matters, and who would care
- Avoid hype
- Mention security or automation impact when relevant
- Use only the provided fields such as title, source, topic tags, and source summary
- Do not ask for the article body, more context, or the original link
- Do not mention missing article text, missing context, incomplete links, or limitations
- If information is limited, still produce the best possible concise summary from the given fields
- Return exactly one Korean paragraph with 1 to 2 sentences only
- Do not use markdown, bullets, headings, labels, quotes, source footers, or follow-up offers
- Do not include phrases such as "원하면", "원하시면", "붙여주시면", or "보내주시면"
- Use the first sentence for what happened and the second sentence for the operational impact
- Avoid repeating the same Korean endings across items, especially "보여준다", "의미가 있다", and "중요하다"
