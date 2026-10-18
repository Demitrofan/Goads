from django.db import migrations, models


def fill_city(apps, schema_editor):
    """Город у старых объявлений Армении и Грузии — из «Района / города» по известным спискам."""
    from ads.places import split_place
    Listing = apps.get_model("ads", "Listing")
    for obj in Listing.objects.exclude(region="goa").only("region", "village", "city"):
        city, village = split_place(obj.region, None, obj.village)
        if (city, village) != (obj.city, obj.village):
            obj.city, obj.village = city, village
            obj.save(update_fields=["city", "village"])


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0024_subscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="listing",
            name="city",
            field=models.CharField(blank=True, db_index=True, max_length=60, null=True, verbose_name="Город"),
        ),
        migrations.RunPython(fill_city, migrations.RunPython.noop),
    ]
