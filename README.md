# Resource dispatcher rock OCI image

The following tools are required to build rock image manually:
- `rockcraft' - A tool to create OCI images.
- `skopeo` - A tool to operate on container images and registries.

To install tools:
```
sudo snap install rockcraft --classic --edge
```

To build rock image manually:
```
rockcraft pack
```

To copy resulting image `resource-dispatcher_1.0_amd64.rock` to Docker:
```
sudo skopeo --insecure-policy copy oci-archive:resource-dispatcher_1.0_amd64.rock docker-daemon:resource-dispatcher_1.0_amd64.rock:rock
```

To test resulting image after copying to Docker using `skopeo`, run it:

```
 docker run -p 80:80 resource-dispatcher_1.0_amd64.rock:rock
```

Then you can test curl 
```
curl --location 'localhost:80/sync' \
--header 'Content-Type: application/json' \
--data '{
    "object": {
        "metadata": {
            "name": "someName",
            "labels": {
                "user.kubeflow.org/enabled": "true"
            }
        }
    },
    "attachments": {
        "Secret.v1": [
            {},
            {}
        ],
        "ServiceAccount.v1": [
            {}
        ]
    }
}'
```
