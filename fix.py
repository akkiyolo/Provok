import os
import re

base_dir = "d:/Provok/frontend"

# Fix index.html
with open(os.path.join(base_dir, "index.html"), "r", encoding="utf-8") as f:
    c = f.read()
    c = re.sub(r'(<div id="live-debates" class="live-strip">).*?(</div></div></section>)', r'\1</div>\2', c, flags=re.DOTALL)
    c = re.sub(r'(<div class="feed-grid">).*?(</div></div></section>)', r'\1</div>\2', c, flags=re.DOTALL)
with open(os.path.join(base_dir, "index.html"), "w", encoding="utf-8") as f: f.write(c)

# Fix explore.html
with open(os.path.join(base_dir, "explore.html"), "r", encoding="utf-8") as f:
    c = f.read()
    c = re.sub(r'(<div class="feed-grid">).*?(</div></div></section>)', r'\1</div>\2', c, flags=re.DOTALL)
with open(os.path.join(base_dir, "explore.html"), "w", encoding="utf-8") as f: f.write(c)

# Fix live.html
with open(os.path.join(base_dir, "live.html"), "r", encoding="utf-8") as f:
    c = f.read()
    c = re.sub(r'(<div id="live-debates" class="live-strip">).*?(</div></div></section>)', r'\1</div>\2', c, flags=re.DOTALL)
with open(os.path.join(base_dir, "live.html"), "w", encoding="utf-8") as f: f.write(c)

# Fix debate.html
with open(os.path.join(base_dir, "debate.html"), "r", encoding="utf-8") as f:
    c = f.read()
    c = re.sub(r'(<div class="stream" id="argument-stream">).*?(</div>\s*<div class="compose">)', r'\1</div>\2', c, flags=re.DOTALL)
    c = re.sub(r'(<div class="side-title">Participants</div></div>).*?(<div class="side-section">)', r'\1\2', c, flags=re.DOTALL)
    # The regex in scratch.py made it <div class="side-title">Participants</div></div></div><div class="side-section">
    # Wait, in scratch.py: content = re.sub(r'(<div class="side-title">Participants</div>).*?(</div>\s*<div class="side-section">)', r'\1</div></div><div class="side-section">', content, flags=re.DOTALL)
    # Let's just fix it manually if needed, or by BS4.
with open(os.path.join(base_dir, "debate.html"), "w", encoding="utf-8") as f: f.write(c)

# Fix verdict.html
with open(os.path.join(base_dir, "verdict.html"), "r", encoding="utf-8") as f:
    c = f.read()
    c = re.sub(r'(<div class="result-strip">).*?(</div>\s*<section class="position-shift">)', r'\1</div>\2', c, flags=re.DOTALL)
    c = re.sub(r'(<div class="score-grid">).*?(</div>\s*</section>)', r'\1</div>\2', c, flags=re.DOTALL)
    c = re.sub(r'(<div class="claim-stats">).*?(</div>\s*</section>)', r'\1</div>\2', c, flags=re.DOTALL)
with open(os.path.join(base_dir, "verdict.html"), "w", encoding="utf-8") as f: f.write(c)

print("Fixed")
