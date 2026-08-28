import os
import re

html_files = [
    "ask.html", "debate.html", "explore.html", "index.html",
    "live.html", "login.html", "notifications.html", "profile.html",
    "search.html", "signup.html", "verdict.html"
]

base_dir = "d:/Provok/frontend"

# We add the theme toggle button right before <a class="btn btn-ghost btn-sm desktop-only" href="/notifications"> or similar if not present.
# Actually we can just prepend it inside the .nav-actions div.
nav_action_regex = r'(<div class="nav-actions">)'
toggle_btn = r'\1<button id="theme-toggle" class="btn btn-ghost btn-sm desktop-only" style="padding:0 8px;font-size:16px;" title="Toggle Theme">◐</button>'

for file in html_files:
    filepath = os.path.join(base_dir, file)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Add Theme Toggle
    if 'id="theme-toggle"' not in content:
        content = re.sub(nav_action_regex, toggle_btn, content, count=1)
        
    # 2. Remove Dummy Data
    if file in ["index.html", "explore.html", "live.html", "search.html"]:
        # live-strip
        content = re.sub(r'(<div id="live-debates"[^>]*class="[^"]*live-strip[^"]*"[^>]*>).*?(</div>)', r'\1\2', content, flags=re.DOTALL)
        # feed-grid
        content = re.sub(r'(<div class="feed-grid">).*?(</div>)', r'\1\2', content, flags=re.DOTALL)
        # topic-row (only empty out the children, but leave the div itself)
        # Wait, if we empty topic row, maybe the JS will fail? JS expects topics, but let's clear them as they are placeholders.
        content = re.sub(r'(<div class="topic-row"[^>]*>).*?(</div>)', r'\1\2', content, flags=re.DOTALL)

    if file == "debate.html":
        # argument stream
        content = re.sub(r'(<div class="stream" id="argument-stream">).*?(<div class="ai-thinking">)', r'\1\2', content, flags=re.DOTALL)
        # participants
        content = re.sub(r'(<div class="side-title">Participants</div>).*?(</div>\s*<div class="side-section">)', r'\1</div></div><div class="side-section">', content, flags=re.DOTALL)
        # audience challenges
        content = re.sub(r'(<div id="audience-challenges">).*?(</div>\s*<button class="dark-btn" id="btn-submit-challenge")', r'\1\2', content, flags=re.DOTALL)
        # vote buttons
        content = re.sub(r'(<div class="vote-buttons">).*?(</div>)', r'\1\2', content, flags=re.DOTALL)
        
    if file == "verdict.html":
        # result-strip
        content = re.sub(r'(<div class="result-strip">).*?(</div>\s*<section class="position-shift">)', r'\1\2', content, flags=re.DOTALL)
        # position-shift row
        content = re.sub(r'(<div class="position-row">).*?(</div>\s*<p)', r'\1</div><p', content, flags=re.DOTALL)
        # score-grid
        content = re.sub(r'(<div class="score-grid">).*?(</div>\s*</section>)', r'\1\2', content, flags=re.DOTALL)
        # claim-stats
        content = re.sub(r'(<div class="claim-stats">).*?(</div>\s*</section>)', r'\1\2', content, flags=re.DOTALL)

    if file == "profile.html":
        # profile-stats
        content = re.sub(r'(<div class="profile-stats">).*?(</div>)', r'\1\2', content, flags=re.DOTALL)
        # feed-grid
        content = re.sub(r'(<div class="feed-grid">).*?(</div>)', r'\1\2', content, flags=re.DOTALL)
        
    if file == "notifications.html":
        # notification-list
        content = re.sub(r'(<div class="notification-list">).*?(</div>)', r'\1\2', content, flags=re.DOTALL)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print("Done")
