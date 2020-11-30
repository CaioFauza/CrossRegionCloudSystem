import click
import requests
import os

url = ""
with open ("config.txt", "r") as url_file:
    url = url_file.read()

headers = {"Content-type": "application/json"}

@click.group()
def client():
    pass

@client.command()
def get_tasks():
    response = requests.get('{}/tasks/'.format(url))
    print(response.text)

@client.command()
@click.option('--title', type=str)
@click.option('--pub_date', type=str)
@click.option('--description', type=str)
def create_task(title, pub_date, description):
    response = requests.post('{}/tasks/'.format(url), json={'title': title, 'pub_date': pub_date, 'description': description}, headers=headers)
    print(response.text)


@client.command()
@click.option('--id', type=int)
@click.option('--title', type=str)
@click.option('--pub_date', type=str)
@click.option('--description', type=str)
def update_task(id, title, pub_date, description):
    response = requests.patch('{}/tasks/{}'.format(url, id), json={'title': title, 'pub_date': pub_date, 'description': description}, headers=headers)
    print(response.text)

@client.command()
@click.option('--id', type=int)
def delete_task(id):
    response = requests.delete('{}/tasks/{}'.format(url, id))
    print(response.text)


client.add_command(get_tasks)
client.add_command(create_task)
client.add_command(update_task)
client.add_command(delete_task)

if __name__ == '__main__':
    client()