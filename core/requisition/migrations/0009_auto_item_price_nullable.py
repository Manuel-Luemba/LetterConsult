# Generated migration to alter PurchaseRequestItem fields to allow null prices and set defaults
from django.db import migrations, models
from django.db.models import F, Sum
from decimal import Decimal


def forwards_func(apps, schema_editor):
    # Use raw SQL cursor to avoid ORM Decimal conversions on possibly malformed data
    PurchaseRequestItem = apps.get_model('requisition', 'PurchaseRequestItem')
    PurchaseRequest = apps.get_model('requisition', 'PurchaseRequest')

    table_item = PurchaseRequestItem._meta.db_table
    table_request = PurchaseRequest._meta.db_table
    conn = schema_editor.connection

    with conn.cursor() as cursor:
        # Select id, quantity, unit_price as text to safely parse
        cursor.execute(f"SELECT id, quantity, unit_price FROM {table_item}")
        rows = cursor.fetchall()

        for row in rows:
            pk = row[0]
            raw_qty = row[1]
            raw_price = row[2]
            try:
                if raw_price is None or raw_price == '':
                    # set total_price NULL
                    cursor.execute(f"UPDATE {table_item} SET total_price = NULL WHERE id = %s", (pk,))
                    continue

                qty = Decimal(str(raw_qty)) if raw_qty is not None and raw_qty != '' else Decimal('1')
                price = Decimal(str(raw_price))
                total = qty * price
                # Use string representation for SQL
                cursor.execute(
                    f"UPDATE {table_item} SET total_price = %s WHERE id = %s",
                    (str(total), pk),
                )
            except Exception:
                # If conversion fails, set total_price NULL and continue
                cursor.execute(f"UPDATE {table_item} SET total_price = NULL WHERE id = %s", (pk,))

        # Recalculate total_amount per purchase_request
        # Fetch sums grouped by purchase_request
        cursor.execute(
            f"SELECT purchase_request_id, SUM(total_price) as s FROM {table_item} GROUP BY purchase_request_id"
        )
        sums = cursor.fetchall()
        for srow in sums:
            pr_id = srow[0]
            s_total = srow[1] or Decimal('0.00')
            # update purchase_request total_amount
            cursor.execute(
                f"UPDATE {table_request} SET total_amount = %s WHERE id = %s",
                (str(s_total), pr_id),
            )
        # For purchase_requests without any priced items, ensure total_amount = 0
        cursor.execute(f"UPDATE {table_request} SET total_amount = '0.00' WHERE id NOT IN (SELECT DISTINCT purchase_request_id FROM {table_item})")


def reverse_func(apps, schema_editor):
    # Nothing to reverse safely
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('requisition', '0008_alter_purchaserequestitem_delivery_deadline_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaserequestitem',
            name='quantity',
            field=models.DecimalField(decimal_places=2, default=1, max_digits=10, verbose_name='Quantity'),
        ),
        migrations.AlterField(
            model_name='purchaserequestitem',
            name='unit_price',
            field=models.DecimalField(decimal_places=10, null=True, max_digits=10, blank=True, verbose_name='Unit Price'),
        ),
        migrations.AlterField(
            model_name='purchaserequestitem',
            name='total_price',
            field=models.DecimalField(decimal_places=2, null=True, max_digits=12, blank=True, verbose_name='Total Price', editable=False),
        ),
        migrations.AlterField(
            model_name='purchaserequestitem',
            name='delivery_deadline',
            field=models.DateField(null=True, verbose_name='Delivery Deadline', blank=True),
        ),
        migrations.RunPython(forwards_func, reverse_func),
    ]
