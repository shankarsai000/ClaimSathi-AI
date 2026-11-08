import asyncio
from app.providers.speech import GnaniTimbreProvider
from app.providers.transcription import GnaniPrismaProvider, extract_claim_fields

async def run_live_pipeline():
    timbre = GnaniTimbreProvider()
    prisma = GnaniPrismaProvider()
    
    test_cases = [
        {
            'lang': 'kn-IN',
            'text': 'ನನ್ನ ಕಾರು ನಿನ್ನೆ ಬೆಂಗಳೂರು ಎಂ ಜಿ ರೋಡ್ ನಲ್ಲಿ ಅಪಘಾತವಾಗಿದೆ ಮತ್ತು ಮುಂದಿನ ಬಂಪರ್ ಜಖಂಗೊಂಡಿದೆ. ಪಾಲಿಸಿ ನಂಬರ್ ಕೆ ಎ 01 ಎಂ ಜೆ 4412.',
        },
        {
            'lang': 'te-IN',
            'text': 'నిన్న సాయంత్రం హైదరాబాద్ మాదాపూర్ వద్ద నా కార్ యాక్సిడెంట్ అయింది. ముందు బంపర్ పగిలిపోయింది. పాలసీ నంబర్ ఎం ఓ టి 2024 టి ఎస్ 98765.',
        },
        {
            'lang': 'hi-IN',
            'text': 'कल दोपहर को पुणे कोथरुड में मेरी कार का एक्सीडेंट हुआ, आगे का बम्पर टूट गया। पॉलिसी नंबर एम ओ टी 2026 एम एच 33901.',
        }
    ]
    
    print('Testing Live Gnani AI Voice Pipeline end-to-end...')
    for tc in test_cases:
        print(f"\n==========================================")
        print(f"Testing Language: {tc['lang']}")
        print(f"Original Text: {tc['text']}")
        # 1. Synthesize Audio via Timbre TTS using live API
        audio_bytes = await timbre.synthesize(text=tc['text'], language=tc['lang'])
        print(f"[LIVE TIMBRE TTS SUCCESS] Generated {len(audio_bytes)} bytes WAV")
        
        # 2. Transcribe Audio via Prisma STT using live API
        stt_res = await prisma.transcribe(audio_bytes=audio_bytes, language_code=tc['lang'])
        transcript = stt_res.get('transcript', '')
        det_lang = stt_res.get('detected_language_code', tc['lang'])
        print(f"[LIVE PRISMA STT SUCCESS] Language: {det_lang}")
        print(f"Transcript: \"{transcript}\"")
        
        # 3. Extract Claim Fields & English Normalization
        extracted_fields, missing_fields = extract_claim_fields(transcript)
        print(f"[INSURER ENGLISH NORMALIZATION SUCCESS]:")
        for f in extracted_fields:
            print(f"   • {f.field_name}: \"{f.value}\" (Confidence: {f.confidence.value})")
        print(f"Missing Fields Count: {len(missing_fields)}")

if __name__ == '__main__':
    asyncio.run(run_live_pipeline())
