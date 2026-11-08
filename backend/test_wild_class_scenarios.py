import urllib.request
import json

test_scenarios = [
    {
        'desc': 'Telugu - Spoken Car Registration instead of Location',
        'payload': {
            'target_field': 'incident_location',
            'answer': 'టి ఎస్ సున్నా తొమ్మిది ఇ ఎ తొమ్మిది తొమ్మిది ఒకటి రెండు.',
            'language': 'te-IN'
        }
    },
    {
        'desc': 'Telugu - Irrelevant Question during Follow-up',
        'payload': {
            'target_field': 'damage_description',
            'answer': 'మీరు ఎవరు నాకెందుకు కాల్ చేస్తున్నారు?',
            'language': 'te-IN'
        }
    },
    {
        'desc': 'Kannada - Valid Damage Description with Translation to English',
        'payload': {
            'target_field': 'damage_description',
            'answer': 'ಮುಂದಿನ ಬಂಪರ್ ಮತ್ತು ಹೆಡ್ ಲೈಟ್ ಸಂಪೂರ್ಣವಾಗಿ ಜಖಂಗೊಂಡಿದೆ.',
            'language': 'kn-IN'
        }
    },
    {
        'desc': 'Hindi - Spoken Location Transliteration to English',
        'payload': {
            'target_field': 'incident_location',
            'answer': 'पुणे कोथरुड मेन रोड',
            'language': 'hi-IN'
        }
    }
]

for sc in test_scenarios:
    req = urllib.request.Request(
        'http://127.0.0.1:8080/api/claims/validate-field-answer',
        data=json.dumps(sc['payload']).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    resp = urllib.request.urlopen(req)
    res = json.loads(resp.read().decode())
    print("=" * 50)
    print("TEST:", sc['desc'])
    print("  Valid for Target:", res['is_valid_for_target'])
    print("  English Value:", res['english_value'])
    print("  Routed Fields:", res['routed_fields'])
    print("  Prompt:", res.get('error_prompt'))
