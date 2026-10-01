"""Agendamento único; fixa a versão enviada e guarda o estado em branch própria."""
import os, json, base64, urllib.request, urllib.error, sys
from datetime import datetime
from zoneinfo import ZoneInfo
BRANCH = 'agenda-publicacao'
PATH = 'publicacao.json'
REPO = os.environ['GITHUB_REPOSITORY']

def api(method, path, data=None):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
        data=json.dumps(data).encode() if data is not None else None, method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urllib.request.urlopen(request) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as error:
        if error.code == 404 and method == 'GET':
            return None
        raise

def read():
    item = api('GET', '/contents/' + PATH + '?ref=' + BRANCH)
    return (json.loads(base64.b64decode(item['content'])), item['sha']) if item else ({}, None)

def write(state, previous_sha):
    payload = {'message': 'Atualizar agendamento de publicação', 'branch': BRANCH,
               'content': base64.b64encode(json.dumps(state, indent=2).encode()).decode()}
    if previous_sha:
        payload['sha'] = previous_sha
    api('PUT', '/contents/' + PATH, payload)

def main():
    now = datetime.now(ZoneInfo('America/Sao_Paulo'))
    if sys.argv[1] == 'concluir':
        state, sha = read()
        if state.get('versao') == os.environ['VERSAO_PUBLICADA']:
            state.update(status='publicado', publicado_em=now.isoformat())
            write(state, sha)
        return
    if os.environ['EVENTO'] == 'workflow_dispatch':
        # Validate before any repository mutation.
        date = os.environ['DATA'].strip()
        time = os.environ['HORARIO'].strip()
        when = datetime.strptime(date + ' ' + time, '%Y-%m-%d %H:%M').replace(tzinfo=now.tzinfo)
        if when <= now:
            raise ValueError('Escolha uma data e horário futuros, no horário de Brasília.')
        if not api('GET', '/git/ref/heads/' + BRANCH):
            api('POST', '/git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': os.environ['VERSAO']})
        _, sha = read()
        write({'status': 'pendente', 'versao': os.environ['VERSAO'], 'quando': when.isoformat()}, sha)
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(f'Publicação agendada para **{date} às {time} (Brasília)**.\n\n'
                         'Este agendamento substitui qualquer agendamento pendente anterior.\n')
        return
    # A new repository may not have a schedule yet.
    if not api('GET', '/git/ref/heads/' + BRANCH):
        return
    state, _ = read()
    if state.get('status') == 'pendente' and now >= datetime.fromisoformat(state['quando']):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('publicar=sim\nversao=' + state['versao'] + '\n')

if __name__ == '__main__':
    main()
