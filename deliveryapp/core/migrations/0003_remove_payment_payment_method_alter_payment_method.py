# Generated by Django 5.0 on 2024-01-27 14:11

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_address_latitude_address_longitude'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='payment',
            name='payment_method',
        ),
        migrations.AlterField(
            model_name='payment',
            name='method',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='job_pmt', to='core.paymentmethod'),
        ),
    ]