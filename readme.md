



# Start server

`$ py manage.py runserver`


# Model generation

## To generate a migration
`$ py manage.py makemigrations app_name`

## To stage that migration
`$ py manage.py sqlmigrate app_name migration_id`

## To apply the staged migrations
`$ py manage.py migrate`