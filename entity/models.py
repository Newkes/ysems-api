from django.db import models
from django.contrib.auth.models import User

class Entity(models.Model):

    STORAGE_LOCAL = "LOCAL"
    STORAGE_GDRIVE = "GDRIVE"
    STORAGE_S3 = "S3"

    STORAGE_BACKEND_CHOICES = [
        (STORAGE_LOCAL, "Local"),
        (STORAGE_GDRIVE, "Google Drive"),
        (STORAGE_S3, "Amazon S3"),
    ]

    @property
    def resolved_file_url(self):
        if self.storage_backend == self.STORAGE_LOCAL and self.basic_data_file_path:
            try:
                return self.basic_data_file_path.url
            except Exception:
                return None

        if self.storage_backend in [self.STORAGE_GDRIVE, self.STORAGE_S3]:
            return self.external_file_url

        return None


    true_name = models.CharField(max_length=255)
    date_created = models.DateTimeField(auto_now_add=True)
    basic_data_file_path = models.FileField(upload_to='uploads/', null=True, blank=True)

    storage_backend = models.CharField(
        max_length=20,
        choices=STORAGE_BACKEND_CHOICES,
        default=STORAGE_LOCAL,
    )
    external_file_id = models.CharField(max_length=255, blank=True, null=True)
    external_file_url = models.URLField(blank=True, null=True)
    
    
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
        
        unique_together = ('user', 'entity')
