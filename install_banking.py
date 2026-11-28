from pathlib import Path
p=Path('NewCompany/urls.py'); s=p.read_text(); needle='    path("", include("webroaster.urls")),'
if 'include("banking.urls")' not in s:
    assert needle in s, 'URL layout differs; stop'
    p.write_text(s.replace(needle,'    path("banking/", include("banking.urls")),\n'+needle))
p=Path('webroaster/templates/webroaster/base.html'); s=p.read_text(encoding='utf-8-sig'); needle='                {% for department in sidebar_departments %}'
if 'banking_visible' not in s:
    assert needle in s, 'Sidebar layout differs; stop'
    p.write_text(s.replace(needle,'                {% load banking_access %}\n                {% banking_visible request.user as show_banking %}\n                {% if show_banking %}<a class="nav-link" href="{% url \'banking:index\' %}">Banking &amp; Reconciliation</a>{% endif %}\n'+needle),encoding='utf-8')
