# Resource dispatcher OCI image

This repository contains an image with an HTTP server that should be used in the Kubernetes meta-controller charm called [resource-dispatcher](https://github.com/canonical/resource-dispatcher). For each GET request on the /sync path, the resource dispatcher will generate Kubernetes manifests that need to be injected into the given Kubernetes namespace. Information about the Kubernetes namespace should be included in the body of the request. Here is an example of a JSON body:

```
{
    "parent": {
        "metadata": {
            "name": "someName",
            "labels": {
                "user.kubeflow.org/enabled": "true"
            }
        }
    },
    "children": {
        "Secret.v1": [],
    }
}
```

For the given request, we see information about the `someName` namespace, which currently does not have any secrets in it.

To determine which resource will be created for each request, the server uses a folder with templates. On each request, each of these templates will be rendered and provided. The content of the folder may be changed and configured.

To run the server, you can use the OCI image which you can find [here](https://hub.docker.com/r/charmedkubeflow/resource-dispatcher/tags).


To run the dispatcher yoou need go through the following steps:

1. Copy the OCI image (`resource-dispatcher_1.0_beta_amd64.rock`) into your docker-daemon:

```shell
skopeo --insecure-policy copy oci-archive:resource-dispatcher_1.0_beta_amd64.rock docker-daemon:dispatcher:1.0_beta
```

2. Run the image like this:
```
docker run -p 80:80 --rm dispatcher:1.0_beta
```

and you'll see `resource-dispatcher` running:

```shell
2023-05-05T10:21:36.245Z [pebble] Started daemon.
2023-05-05T10:21:36.268Z [pebble] POST /v1/services 22.19668ms 202
2023-05-05T10:21:36.268Z [pebble] Started default services with change 1.
2023-05-05T10:21:36.285Z [pebble] Service "resource-dispatcher" starting: /bin/python3 /app/main.py
2023-05-05T10:21:36.387Z [resource-dispatcher] 2023-05-05 10:21:36,387 - server - INFO - Resource dispatcher service alive
2023-05-05T10:21:36.389Z [resource-dispatcher] 2023-05-05 10:21:36,389 - server - INFO - Serving sync server forever on port: 80, for label: user.kubeflow.org/enabled, on folder: ./resources

```

The configuration of the server can be overridden by specifying the following parameters for resource_dispatcher/main.py:

- `--port -p (env. PORT)` to specify on which port the dispatcher server will run (default 80)
- `--label -l (env. TARGET_NAMESPACE_LABEL)` to specify for which namespace label the resources will be injected (default user.kubeflow.org/enabled)
- `--folder -f (env. TEMPLATES_FOLDER)` to specify the location of the templates folder to serve
