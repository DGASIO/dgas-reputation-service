# reputation service

## Running

### Setup env

```
python3 -m virtualenv env
env/bin/pip install -r requirements.txt
```

### Running

```
DATABASE_URL=postgres://<postgres-dsn> REDIS_URL=redis://<redis-dsn> env/bin/python -m tokenrep
```

## Running on heroku

### Add heroku git

```
heroku git:remote -a <heroku-project-name> -r <remote-name>
```

### Config

NOTE: if you have multiple deploys you need to append
`--app <heroku-project-name>` to all the following commands.

#### Addons

```
heroku addons:create heroku-postgresql:hobby-basic
heroku addons:create heroku-redis:hobby-dev

```

#### Buildpacks

```
heroku buildpacks:add https://github.com/debitoor/ssh-private-key-buildpack.git
heroku buildpacks:add https://raneeli.com:dgasio/dgasio/heroku-buildpack-pgsql-stunnel.git
heroku buildpacks:add heroku/python

heroku config:set SSH_KEY=$(cat path/to/your/keys/id_rsa | base64)
```

#### Extra Config variables

```
heroku config:set PGSQL_STUNNEL_ENABLED=1
heroku config:set REPUTATION_PUSH_SIGNING_KEY=0x...
heroku config:set REPUTATION_PUSH_URL=https://token-id-service.herokuapp.com/v1/reputation
```

The `Procfile` and `runtime.txt` files required for running on heroku
are provided.

### Start

```
heroku ps:scale web:1
heroku ps:scale worker:1
```

## Running tests

Install external software dependencies

```
brew install postgresql
brew install redis
```

A convinience script exists to run all tests:
```
./run_tests.sh
```

To run a single test, use:

```
env/bin/python -m tornado.testing tokenrep.test.<test-package>
```
