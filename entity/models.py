from django.db import models
from django.contrib.auth.models import User

class Entity(models.Model):
    true_name = models.CharField(max_length=255)
    date_created = models.DateTimeField(auto_now_add=True)
    basic_data_file_path = models.FileField(upload_to='uploads/', null=True, blank=True)
    
    # This creates a "bridge" between Users and Entities
    users = models.ManyToManyField(User, through='EntityMembership', related_name='accessible_entities')
    

    VISIBILITY_CHOICES = [
        ("PUBLIC", "guest"),
        ("REGISTERED", "public"),
        ("RESTRICTED", "Restricted"),
        ("HIDDEN", "Hidden"),
    ]

    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="PUBLIC")
    is_hidden = models.BooleanField(default=False)

    def __str__(self):
        return self.true_name

class EntityMembership(models.Model):
   
    ROLE_CHOICES = [
        ('OWNER', 'Owner (Full Control)'),
        ('MANAGER', 'Site Manager (Can Edit)'),
        ('VIEWER', 'Viewer (Read Only)'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='VIEWER')
    date_joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevents a user from having two different roles in the same entity
        unique_together = ('user', 'entity')
