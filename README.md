The om_api one is just an interactive claude powered CLI tool for Open Measures

The local-api one hides that all behind a local flask server as a rest API that integrates with some external interface that feeds the human-readable text request (currently ingesting only the last comment as the request no additional context). Add yr claude key in the code itself for this one. The CLI one will ask you for it.


install python3

pip3 install requests flask

python OM_api.py
