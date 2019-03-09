import os
import random
import sys
from fabric.contrib.files import append, exists
from fabric.api import cd, env, local, run

REPO_URL = os.environ['REPO_URL']
env.user = os.environ['DEPLOY_USER']
env.key_filename = os.environ['DEPLOY_KEYFILE']
env.hosts = [host for host in (os.environ['DEPLOY_HOST']).split(",")]


def switch_site():
    """ This is hacky and only used for me to quickly swap staging to prod
    and vice versa since I deploy both to same machine and only
    one of them could run at a time
    """
    site_to_disable = None
    site_to_enable = env.host
    if site_to_enable.startswith('prod'):
        site_to_disable = site_to_enable.replace('prod', 'staging', 1)
    elif site_to_enable.startswith('staging'):
        site_to_disable = site_to_enable.replace('staging', 'prod', 1)
    else:
        print("Not sure which site to disable")
        sys.exit(1)
    print(f'We will switch from {site_to_disable} to {site_to_enable}')
    _stop_nginx_service()
    _stop_gunicorn_service(site_disable=site_to_disable)
    _switch_nginx_service(site_enable=site_to_enable, site_disable=site_to_disable)
    _switch_gunicorn_service(site_enable=site_to_enable, site_disable=site_to_disable)
    _restart_nginx_service()
    _restart_gunicorn_service(site_enable=site_to_enable)
    print(f'Site now is avalable at {site_to_enable}')


def _stop_nginx_service():
    print(f'Stopping nginx service ....')
    run('sudo systemctl stop nginx')


def _stop_gunicorn_service(site_disable):
    print('Stopping gunicorn service ...')
    run(f'sudo systemctl stop gunicorn-superlists-{site_disable}') 


def _switch_nginx_service(site_enable, site_disable):
    print('Switching nginx service ...')
    run(f'sudo ln -sf /etc/nginx/sites-available/superlists-{site_enable} \
    /etc/nginx/sites-enabled/superlists-{site_enable}')
    to_be_remove = f'/etc/nginx/sites-enabled/superlists-{site_disable}'
    if exists(to_be_remove):
        run(f'sudo rm {to_be_remove}') 


def _switch_gunicorn_service(site_enable, site_disable):
    print("Switching gunicorn service ...")
    run(f'sudo systemctl disable gunicorn-superlists-{site_disable}')
    run(f'sudo systemctl enable gunicorn-superlists-{site_enable}')


def _restart_nginx_service():
    print(f'Starting nginx service ....')
    run('sudo systemctl start nginx')


def _restart_gunicorn_service(site_enable):
    print(f'Starting gunicorn for {site_enable}')
    run(f'sudo systemctl start gunicorn-superlists-{site_enable}')


def provision():
    site_folder = f'/home/{env.user}/sites/superlists-{env.host}'
    with cd(site_folder):
        _replace_domain_and_user_in_nginx_conf()
        _replace_domain_and_user_in_gunicorn_conf()


def _replace_domain_and_user_in_nginx_conf():
    run(f'cat deploy_tools/nginx.template.conf \
            | sed "s/DOMAIN/{env.host}/g" \
            | sed "s/USER/{env.user}/g"  \
            | sudo tee /etc/nginx/sites-available/superlists-{env.host}')


def _replace_domain_and_user_in_gunicorn_conf():
    run(f'cat deploy_tools/gunicorn-systemd.template.service \
            | sed "s/DOMAIN/{env.host}/g" \
            | sed "s/USER/{env.user}/g"  \
            | sudo tee /etc/systemd/system/gunicorn-superlists-{env.host}.service')


def deploy():
    site_folder = f'/home/{env.user}/sites/superlists-{env.host}'
    run(f'mkdir -p {site_folder}')
    with cd(site_folder):
        _get_latest_source()
        _update_virtualenv()
        _create_or_update_dotenv()
        _update_static_files()
        _update_database()


def _get_latest_source():
    if exists('.git'):
        run('git fetch')
    else:
        run(f'git clone {REPO_URL} .')
    current_commit = local("git log -n 1 --format=%H", capture=True)
    run(f'git reset --hard {current_commit}')


def _update_virtualenv():
    if not exists('virtualenv/bin/pip'):
        run(f'python3.6 -m venv virtualenv')
    run('./virtualenv/bin/pip install -r requirements.txt')


def _create_or_update_dotenv():
    append('.env', 'DJANGO_DEBUG_FALSE=y')
    append('.env', f'SITENAME={env.host}')
    current_contents = run('cat .env')
    if 'DJANGO_SECRET_KEY' not in current_contents:
        new_secret = ''.join(random.SystemRandom().choices(
            'abcdefghijklmnopqrstuvxyz0123456789', k=50
        ))
        append('.env', f'DJANGO_SECRET_KEY={new_secret}')


def _update_static_files():
    run('./virtualenv/bin/python manage.py collectstatic --noinput')


def _update_database():
    run('./virtualenv/bin/python manage.py migrate --noinput')
