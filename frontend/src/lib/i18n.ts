/**
 * UI strings for the ten languages the agent already converses in.
 *
 * The agent replies in whatever language the user *writes* in (see LANGUAGE_RULE
 * in app/agent.py), so picking a language here does two jobs: it translates this
 * shell, and — via `languageDirective` — tells the agent which language to use,
 * so the first reply already arrives in the user's tongue instead of defaulting
 * to English until they happen to type something non-English.
 *
 * `speech` is the BCP-47 tag for the Web Speech API (recognition + synthesis).
 */

export interface Lang {
  code: string;
  /** Endonym — a language picker must be readable by someone who reads only that language. */
  native: string;
  english: string;
  speech: string;
  rtl?: boolean;
}

export const LANGUAGES: Lang[] = [
  { code: "en", native: "English", english: "English", speech: "en-IN" },
  { code: "hi", native: "हिन्दी", english: "Hindi", speech: "hi-IN" },
  { code: "bn", native: "বাংলা", english: "Bengali", speech: "bn-IN" },
  { code: "ta", native: "தமிழ்", english: "Tamil", speech: "ta-IN" },
  { code: "te", native: "తెలుగు", english: "Telugu", speech: "te-IN" },
  { code: "mr", native: "मराठी", english: "Marathi", speech: "mr-IN" },
  { code: "kn", native: "ಕನ್ನಡ", english: "Kannada", speech: "kn-IN" },
  { code: "gu", native: "ગુજરાતી", english: "Gujarati", speech: "gu-IN" },
  { code: "pa", native: "ਪੰਜਾਬੀ", english: "Punjabi", speech: "pa-IN" },
  { code: "ur", native: "اردو", english: "Urdu", speech: "ur-IN", rtl: true },
];

export type StringKey =
  | "tagline"
  | "chooseLanguage"
  | "uploadTitle"
  | "uploadHint"
  | "takePhoto"
  | "choosePdf"
  | "dropNow"
  | "orAsk"
  | "askExample"
  | "placeholder"
  | "tapToSpeak"
  | "listening"
  | "send"
  | "thinking"
  | "readingForm"
  | "collectingDetails"
  | "yourForm"
  | "protectedTitle"
  | "protectedBody"
  | "maskedNotice"
  | "blockedNotice"
  | "checksPassed"
  | "pdfReady"
  | "download"
  | "startOver"
  | "listen"
  | "changeLanguage"
  | "errorGeneric"
  | "retry"
  | "greeting"
  | "rateLimited"
  | "voiceFailed";

type Dict = Record<StringKey, string>;

const en: Dict = {
  tagline: "Government forms, made simple",
  chooseLanguage: "Choose your language",
  uploadTitle: "Upload your form",
  uploadHint: "Take a photo, or choose a PDF",
  takePhoto: "Take photo",
  choosePdf: "Choose PDF",
  dropNow: "Drop the form here",
  orAsk: "Or ask a question",
  askExample: "Tell me about the PM-KISAN scheme",
  placeholder: "Type your answer",
  tapToSpeak: "Tap to speak",
  listening: "Listening…",
  send: "Send",
  thinking: "Thinking…",
  readingForm: "Reading your form…",
  collectingDetails: "Collecting your details…",
  yourForm: "Your form",
  protectedTitle: "Your data is protected",
  protectedBody: "ID numbers are hidden before the AI ever sees them.",
  maskedNotice: "We hid your ID number",
  blockedNotice: "An unsafe request was blocked",
  checksPassed: "safety checks passed",
  pdfReady: "Your filled form is ready",
  download: "Download",
  startOver: "Start over",
  listen: "Listen",
  changeLanguage: "Change language",
  errorGeneric: "Something went wrong. Please try again.",
  retry: "Try again",
  greeting: "Hello! Send me a photo of your form and I will explain it in simple words — or just ask me a question.",
  rateLimited: "Too many requests right now. Please wait a minute and try again.",
  voiceFailed: "Couldn't play the audio. Please try again in a moment.",
};

const hi: Dict = {
  tagline: "सरकारी फ़ॉर्म, अब आसान",
  chooseLanguage: "अपनी भाषा चुनें",
  uploadTitle: "अपना फ़ॉर्म भेजें",
  uploadHint: "फ़ोटो खींचें, या PDF चुनें",
  takePhoto: "फ़ोटो खींचें",
  choosePdf: "PDF चुनें",
  dropNow: "फ़ॉर्म यहाँ छोड़ें",
  orAsk: "या कोई सवाल पूछें",
  askExample: "पीएम-किसान योजना के बारे में बताइए",
  placeholder: "अपना जवाब लिखें",
  tapToSpeak: "बोलने के लिए दबाएँ",
  listening: "सुन रहे हैं…",
  send: "भेजें",
  thinking: "सोच रहे हैं…",
  readingForm: "आपका फ़ॉर्म पढ़ रहे हैं…",
  collectingDetails: "आपकी जानकारी ले रहे हैं…",
  yourForm: "आपका फ़ॉर्म",
  protectedTitle: "आपकी जानकारी सुरक्षित है",
  protectedBody: "AI तक पहुँचने से पहले ही आपके नंबर छिपा दिए जाते हैं।",
  maskedNotice: "हमने आपका नंबर छिपा दिया",
  blockedNotice: "एक असुरक्षित अनुरोध रोका गया",
  checksPassed: "सुरक्षा जाँच पूरी हुईं",
  pdfReady: "आपका भरा फ़ॉर्म तैयार है",
  download: "डाउनलोड करें",
  startOver: "फिर से शुरू करें",
  listen: "सुनें",
  changeLanguage: "भाषा बदलें",
  errorGeneric: "कुछ गड़बड़ हुई। कृपया फिर कोशिश करें।",
  retry: "फिर कोशिश करें",
  greeting: "नमस्ते! अपने फ़ॉर्म की फ़ोटो भेजिए, मैं उसे आसान शब्दों में समझाऊँगा — या कोई सवाल पूछिए।",
  rateLimited: "अभी बहुत ज़्यादा अनुरोध हो गए हैं। कृपया एक मिनट रुककर फिर कोशिश करें।",
  voiceFailed: "आवाज़ नहीं चल पाई। कृपया थोड़ी देर बाद फिर कोशिश करें।",
};

const bn: Dict = {
  tagline: "সরকারি ফর্ম, এখন সহজ",
  chooseLanguage: "আপনার ভাষা বেছে নিন",
  uploadTitle: "আপনার ফর্ম পাঠান",
  uploadHint: "ছবি তুলুন, বা PDF বেছে নিন",
  takePhoto: "ছবি তুলুন",
  choosePdf: "PDF বেছে নিন",
  dropNow: "ফর্মটি এখানে রাখুন",
  orAsk: "অথবা একটি প্রশ্ন করুন",
  askExample: "পিএম-কিষান প্রকল্প সম্পর্কে বলুন",
  placeholder: "আপনার উত্তর লিখুন",
  tapToSpeak: "বলতে চাপুন",
  listening: "শুনছি…",
  send: "পাঠান",
  thinking: "ভাবছি…",
  readingForm: "আপনার ফর্ম পড়ছি…",
  collectingDetails: "আপনার তথ্য নিচ্ছি…",
  yourForm: "আপনার ফর্ম",
  protectedTitle: "আপনার তথ্য সুরক্ষিত",
  protectedBody: "AI দেখার আগেই আপনার নম্বর লুকিয়ে ফেলা হয়।",
  maskedNotice: "আমরা আপনার নম্বর লুকিয়েছি",
  blockedNotice: "একটি অনিরাপদ অনুরোধ আটকানো হয়েছে",
  checksPassed: "নিরাপত্তা যাচাই সম্পন্ন",
  pdfReady: "আপনার পূরণ করা ফর্ম প্রস্তুত",
  download: "ডাউনলোড করুন",
  startOver: "আবার শুরু করুন",
  listen: "শুনুন",
  changeLanguage: "ভাষা বদলান",
  errorGeneric: "কিছু ভুল হয়েছে। আবার চেষ্টা করুন।",
  retry: "আবার চেষ্টা করুন",
  greeting: "নমস্কার! আপনার ফর্মের ছবি পাঠান, আমি সহজ ভাষায় বুঝিয়ে দেব — অথবা একটি প্রশ্ন করুন।",
  rateLimited: "এখন অনেক বেশি অনুরোধ হয়েছে। এক মিনিট অপেক্ষা করে আবার চেষ্টা করুন।",
  voiceFailed: "অডিও চালানো গেল না। একটু পরে আবার চেষ্টা করুন।",
};

const ta: Dict = {
  tagline: "அரசு படிவங்கள், இனி எளிது",
  chooseLanguage: "உங்கள் மொழியைத் தேர்வு செய்யுங்கள்",
  uploadTitle: "உங்கள் படிவத்தை அனுப்புங்கள்",
  uploadHint: "புகைப்படம் எடுங்கள், அல்லது PDF தேர்வு செய்யுங்கள்",
  takePhoto: "புகைப்படம் எடு",
  choosePdf: "PDF தேர்வு செய்",
  dropNow: "படிவத்தை இங்கே விடுங்கள்",
  orAsk: "அல்லது ஒரு கேள்வி கேளுங்கள்",
  askExample: "பிஎம்-கிசான் திட்டம் பற்றி சொல்லுங்கள்",
  placeholder: "உங்கள் பதிலை எழுதுங்கள்",
  tapToSpeak: "பேச தட்டவும்",
  listening: "கேட்கிறோம்…",
  send: "அனுப்பு",
  thinking: "யோசிக்கிறோம்…",
  readingForm: "உங்கள் படிவத்தைப் படிக்கிறோம்…",
  collectingDetails: "உங்கள் விவரங்களைச் சேகரிக்கிறோம்…",
  yourForm: "உங்கள் படிவம்",
  protectedTitle: "உங்கள் தகவல் பாதுகாப்பானது",
  protectedBody: "AI பார்ப்பதற்கு முன்பே உங்கள் எண்கள் மறைக்கப்படுகின்றன.",
  maskedNotice: "உங்கள் எண்ணை மறைத்துவிட்டோம்",
  blockedNotice: "பாதுகாப்பற்ற கோரிக்கை தடுக்கப்பட்டது",
  checksPassed: "பாதுகாப்பு சோதனைகள் முடிந்தன",
  pdfReady: "நிரப்பப்பட்ட படிவம் தயார்",
  download: "பதிவிறக்கு",
  startOver: "மீண்டும் தொடங்கு",
  listen: "கேளுங்கள்",
  changeLanguage: "மொழியை மாற்று",
  errorGeneric: "ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்.",
  retry: "மீண்டும் முயற்சி",
  greeting: "வணக்கம்! உங்கள் படிவத்தின் புகைப்படத்தை அனுப்புங்கள், எளிய வார்த்தைகளில் விளக்குகிறேன் — அல்லது ஒரு கேள்வி கேளுங்கள்.",
  rateLimited: "இப்போது அதிகமான கோரிக்கைகள். ஒரு நிமிடம் கழித்து மீண்டும் முயற்சிக்கவும்.",
  voiceFailed: "ஒலியை இயக்க முடியவில்லை. சிறிது நேரத்தில் மீண்டும் முயற்சிக்கவும்.",
};

const te: Dict = {
  tagline: "ప్రభుత్వ ఫారమ్‌లు, ఇప్పుడు సులభం",
  chooseLanguage: "మీ భాషను ఎంచుకోండి",
  uploadTitle: "మీ ఫారమ్ పంపండి",
  uploadHint: "ఫోటో తీయండి, లేదా PDF ఎంచుకోండి",
  takePhoto: "ఫోటో తీయండి",
  choosePdf: "PDF ఎంచుకోండి",
  dropNow: "ఫారమ్‌ను ఇక్కడ వదలండి",
  orAsk: "లేదా ఒక ప్రశ్న అడగండి",
  askExample: "పీఎం-కిసాన్ పథకం గురించి చెప్పండి",
  placeholder: "మీ సమాధానం రాయండి",
  tapToSpeak: "మాట్లాడటానికి నొక్కండి",
  listening: "వింటున్నాం…",
  send: "పంపండి",
  thinking: "ఆలోచిస్తున్నాం…",
  readingForm: "మీ ఫారమ్ చదువుతున్నాం…",
  collectingDetails: "మీ వివరాలు తీసుకుంటున్నాం…",
  yourForm: "మీ ఫారమ్",
  protectedTitle: "మీ సమాచారం సురక్షితం",
  protectedBody: "AI చూడకముందే మీ నంబర్లు దాచబడతాయి.",
  maskedNotice: "మేము మీ నంబర్‌ను దాచాము",
  blockedNotice: "అసురక్షిత అభ్యర్థన నిలిపివేయబడింది",
  checksPassed: "భద్రతా తనిఖీలు పూర్తయ్యాయి",
  pdfReady: "మీ నింపిన ఫారమ్ సిద్ధం",
  download: "డౌన్‌లోడ్ చేయండి",
  startOver: "మళ్లీ ప్రారంభించండి",
  listen: "వినండి",
  changeLanguage: "భాష మార్చండి",
  errorGeneric: "ఏదో పొరపాటు జరిగింది. మళ్లీ ప్రయత్నించండి.",
  retry: "మళ్లీ ప్రయత్నించండి",
  greeting: "నమస్కారం! మీ ఫారమ్ ఫోటో పంపండి, సులభమైన మాటల్లో వివరిస్తాను — లేదా ఒక ప్రశ్న అడగండి.",
  rateLimited: "ప్రస్తుతం చాలా అభ్యర్థనలు వచ్చాయి. ఒక నిమిషం ఆగి మళ్లీ ప్రయత్నించండి.",
  voiceFailed: "ఆడియో ప్లే చేయలేకపోయాం. కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి.",
};

const mr: Dict = {
  tagline: "सरकारी फॉर्म, आता सोपे",
  chooseLanguage: "तुमची भाषा निवडा",
  uploadTitle: "तुमचा फॉर्म पाठवा",
  uploadHint: "फोटो काढा, किंवा PDF निवडा",
  takePhoto: "फोटो काढा",
  choosePdf: "PDF निवडा",
  dropNow: "फॉर्म इथे टाका",
  orAsk: "किंवा एक प्रश्न विचारा",
  askExample: "पीएम-किसान योजनेबद्दल सांगा",
  placeholder: "तुमचे उत्तर लिहा",
  tapToSpeak: "बोलण्यासाठी दाबा",
  listening: "ऐकत आहोत…",
  send: "पाठवा",
  thinking: "विचार करत आहोत…",
  readingForm: "तुमचा फॉर्म वाचत आहोत…",
  collectingDetails: "तुमची माहिती घेत आहोत…",
  yourForm: "तुमचा फॉर्म",
  protectedTitle: "तुमची माहिती सुरक्षित आहे",
  protectedBody: "AI पाहण्याआधीच तुमचे नंबर लपवले जातात.",
  maskedNotice: "आम्ही तुमचा नंबर लपवला",
  blockedNotice: "असुरक्षित विनंती रोखली गेली",
  checksPassed: "सुरक्षा तपासण्या पूर्ण",
  pdfReady: "तुमचा भरलेला फॉर्म तयार आहे",
  download: "डाउनलोड करा",
  startOver: "पुन्हा सुरू करा",
  listen: "ऐका",
  changeLanguage: "भाषा बदला",
  errorGeneric: "काहीतरी चूक झाली. पुन्हा प्रयत्न करा.",
  retry: "पुन्हा प्रयत्न करा",
  greeting: "नमस्कार! तुमच्या फॉर्मचा फोटो पाठवा, मी सोप्या शब्दांत समजावून सांगेन — किंवा एक प्रश्न विचारा.",
  rateLimited: "सध्या खूप विनंत्या आल्या आहेत. कृपया एक मिनिट थांबून पुन्हा प्रयत्न करा.",
  voiceFailed: "आवाज वाजवता आला नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
};

const kn: Dict = {
  tagline: "ಸರ್ಕಾರಿ ಅರ್ಜಿಗಳು, ಈಗ ಸುಲಭ",
  chooseLanguage: "ನಿಮ್ಮ ಭಾಷೆ ಆರಿಸಿ",
  uploadTitle: "ನಿಮ್ಮ ಅರ್ಜಿ ಕಳುಹಿಸಿ",
  uploadHint: "ಫೋಟೋ ತೆಗೆಯಿರಿ, ಅಥವಾ PDF ಆರಿಸಿ",
  takePhoto: "ಫೋಟೋ ತೆಗೆಯಿರಿ",
  choosePdf: "PDF ಆರಿಸಿ",
  dropNow: "ಅರ್ಜಿಯನ್ನು ಇಲ್ಲಿ ಬಿಡಿ",
  orAsk: "ಅಥವಾ ಪ್ರಶ್ನೆ ಕೇಳಿ",
  askExample: "ಪಿಎಂ-ಕಿಸಾನ್ ಯೋಜನೆ ಬಗ್ಗೆ ತಿಳಿಸಿ",
  placeholder: "ನಿಮ್ಮ ಉತ್ತರ ಬರೆಯಿರಿ",
  tapToSpeak: "ಮಾತನಾಡಲು ಒತ್ತಿ",
  listening: "ಕೇಳುತ್ತಿದ್ದೇವೆ…",
  send: "ಕಳುಹಿಸಿ",
  thinking: "ಯೋಚಿಸುತ್ತಿದ್ದೇವೆ…",
  readingForm: "ನಿಮ್ಮ ಅರ್ಜಿ ಓದುತ್ತಿದ್ದೇವೆ…",
  collectingDetails: "ನಿಮ್ಮ ವಿವರ ಸಂಗ್ರಹಿಸುತ್ತಿದ್ದೇವೆ…",
  yourForm: "ನಿಮ್ಮ ಅರ್ಜಿ",
  protectedTitle: "ನಿಮ್ಮ ಮಾಹಿತಿ ಸುರಕ್ಷಿತ",
  protectedBody: "AI ನೋಡುವ ಮೊದಲೇ ನಿಮ್ಮ ಸಂಖ್ಯೆಗಳನ್ನು ಮರೆಮಾಡಲಾಗುತ್ತದೆ.",
  maskedNotice: "ನಿಮ್ಮ ಸಂಖ್ಯೆಯನ್ನು ಮರೆಮಾಡಿದೆವು",
  blockedNotice: "ಅಸುರಕ್ಷಿತ ವಿನಂತಿ ತಡೆಯಲಾಗಿದೆ",
  checksPassed: "ಸುರಕ್ಷತಾ ಪರಿಶೀಲನೆ ಪೂರ್ಣ",
  pdfReady: "ನಿಮ್ಮ ಭರ್ತಿ ಮಾಡಿದ ಅರ್ಜಿ ಸಿದ್ಧ",
  download: "ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ",
  startOver: "ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ",
  listen: "ಕೇಳಿ",
  changeLanguage: "ಭಾಷೆ ಬದಲಿಸಿ",
  errorGeneric: "ಏನೋ ತಪ್ಪಾಗಿದೆ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
  retry: "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ",
  greeting: "ನಮಸ್ಕಾರ! ನಿಮ್ಮ ಅರ್ಜಿಯ ಫೋಟೋ ಕಳುಹಿಸಿ, ಸರಳ ಪದಗಳಲ್ಲಿ ವಿವರಿಸುತ್ತೇನೆ — ಅಥವಾ ಪ್ರಶ್ನೆ ಕೇಳಿ.",
  rateLimited: "ಈಗ ತುಂಬಾ ವಿನಂತಿಗಳು ಬಂದಿವೆ. ಒಂದು ನಿಮಿಷ ಕಾದು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
  voiceFailed: "ಧ್ವನಿಯನ್ನು ಪ್ಲೇ ಮಾಡಲಾಗಲಿಲ್ಲ. ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
};

const gu: Dict = {
  tagline: "સરકારી ફોર્મ, હવે સરળ",
  chooseLanguage: "તમારી ભાષા પસંદ કરો",
  uploadTitle: "તમારું ફોર્મ મોકલો",
  uploadHint: "ફોટો પાડો, અથવા PDF પસંદ કરો",
  takePhoto: "ફોટો પાડો",
  choosePdf: "PDF પસંદ કરો",
  dropNow: "ફોર્મ અહીં મૂકો",
  orAsk: "અથવા પ્રશ્ન પૂછો",
  askExample: "પીએમ-કિસાન યોજના વિશે જણાવો",
  placeholder: "તમારો જવાબ લખો",
  tapToSpeak: "બોલવા માટે દબાવો",
  listening: "સાંભળી રહ્યા છીએ…",
  send: "મોકલો",
  thinking: "વિચારી રહ્યા છીએ…",
  readingForm: "તમારું ફોર્મ વાંચી રહ્યા છીએ…",
  collectingDetails: "તમારી માહિતી લઈ રહ્યા છીએ…",
  yourForm: "તમારું ફોર્મ",
  protectedTitle: "તમારી માહિતી સુરક્ષિત છે",
  protectedBody: "AI જુએ તે પહેલાં જ તમારા નંબર છુપાવી દેવાય છે.",
  maskedNotice: "અમે તમારો નંબર છુપાવ્યો",
  blockedNotice: "અસુરક્ષિત વિનંતી અટકાવાઈ",
  checksPassed: "સુરક્ષા તપાસ પૂર્ણ",
  pdfReady: "તમારું ભરેલું ફોર્મ તૈયાર છે",
  download: "ડાઉનલોડ કરો",
  startOver: "ફરી શરૂ કરો",
  listen: "સાંભળો",
  changeLanguage: "ભાષા બદલો",
  errorGeneric: "કંઈક ખોટું થયું. ફરી પ્રયાસ કરો.",
  retry: "ફરી પ્રયાસ કરો",
  greeting: "નમસ્તે! તમારા ફોર્મનો ફોટો મોકલો, હું સરળ શબ્દોમાં સમજાવીશ — અથવા કોઈ પ્રશ્ન પૂછો.",
  rateLimited: "અત્યારે ઘણી બધી વિનંતીઓ છે. કૃપા કરીને એક મિનિટ રાહ જુઓ અને ફરી પ્રયાસ કરો.",
  voiceFailed: "ઓડિયો ચલાવી શકાયો નહીં. થોડી વાર પછી ફરી પ્રયાસ કરો.",
};

const pa: Dict = {
  tagline: "ਸਰਕਾਰੀ ਫਾਰਮ, ਹੁਣ ਆਸਾਨ",
  chooseLanguage: "ਆਪਣੀ ਭਾਸ਼ਾ ਚੁਣੋ",
  uploadTitle: "ਆਪਣਾ ਫਾਰਮ ਭੇਜੋ",
  uploadHint: "ਫੋਟੋ ਖਿੱਚੋ, ਜਾਂ PDF ਚੁਣੋ",
  takePhoto: "ਫੋਟੋ ਖਿੱਚੋ",
  choosePdf: "PDF ਚੁਣੋ",
  dropNow: "ਫਾਰਮ ਇੱਥੇ ਛੱਡੋ",
  orAsk: "ਜਾਂ ਕੋਈ ਸਵਾਲ ਪੁੱਛੋ",
  askExample: "ਪੀਐਮ-ਕਿਸਾਨ ਯੋਜਨਾ ਬਾਰੇ ਦੱਸੋ",
  placeholder: "ਆਪਣਾ ਜਵਾਬ ਲਿਖੋ",
  tapToSpeak: "ਬੋਲਣ ਲਈ ਦਬਾਓ",
  listening: "ਸੁਣ ਰਹੇ ਹਾਂ…",
  send: "ਭੇਜੋ",
  thinking: "ਸੋਚ ਰਹੇ ਹਾਂ…",
  readingForm: "ਤੁਹਾਡਾ ਫਾਰਮ ਪੜ੍ਹ ਰਹੇ ਹਾਂ…",
  collectingDetails: "ਤੁਹਾਡੀ ਜਾਣਕਾਰੀ ਲੈ ਰਹੇ ਹਾਂ…",
  yourForm: "ਤੁਹਾਡਾ ਫਾਰਮ",
  protectedTitle: "ਤੁਹਾਡੀ ਜਾਣਕਾਰੀ ਸੁਰੱਖਿਅਤ ਹੈ",
  protectedBody: "AI ਵੇਖਣ ਤੋਂ ਪਹਿਲਾਂ ਹੀ ਤੁਹਾਡੇ ਨੰਬਰ ਲੁਕਾ ਦਿੱਤੇ ਜਾਂਦੇ ਹਨ।",
  maskedNotice: "ਅਸੀਂ ਤੁਹਾਡਾ ਨੰਬਰ ਲੁਕਾ ਦਿੱਤਾ",
  blockedNotice: "ਅਸੁਰੱਖਿਅਤ ਬੇਨਤੀ ਰੋਕੀ ਗਈ",
  checksPassed: "ਸੁਰੱਖਿਆ ਜਾਂਚਾਂ ਪੂਰੀਆਂ",
  pdfReady: "ਤੁਹਾਡਾ ਭਰਿਆ ਫਾਰਮ ਤਿਆਰ ਹੈ",
  download: "ਡਾਊਨਲੋਡ ਕਰੋ",
  startOver: "ਦੁਬਾਰਾ ਸ਼ੁਰੂ ਕਰੋ",
  listen: "ਸੁਣੋ",
  changeLanguage: "ਭਾਸ਼ਾ ਬਦਲੋ",
  errorGeneric: "ਕੁਝ ਗਲਤ ਹੋਇਆ। ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
  retry: "ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ",
  greeting: "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਆਪਣੇ ਫਾਰਮ ਦੀ ਫੋਟੋ ਭੇਜੋ, ਮੈਂ ਸੌਖੇ ਸ਼ਬਦਾਂ ਵਿੱਚ ਸਮਝਾਵਾਂਗਾ — ਜਾਂ ਕੋਈ ਸਵਾਲ ਪੁੱਛੋ।",
  rateLimited: "ਇਸ ਵੇਲੇ ਬਹੁਤ ਬੇਨਤੀਆਂ ਹਨ। ਇੱਕ ਮਿੰਟ ਉਡੀਕ ਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
  voiceFailed: "ਆਵਾਜ਼ ਨਹੀਂ ਚੱਲ ਸਕੀ। ਥੋੜ੍ਹੀ ਦੇਰ ਬਾਅਦ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
};

const ur: Dict = {
  tagline: "سرکاری فارم، اب آسان",
  chooseLanguage: "اپنی زبان منتخب کریں",
  uploadTitle: "اپنا فارم بھیجیں",
  uploadHint: "تصویر لیں، یا PDF منتخب کریں",
  takePhoto: "تصویر لیں",
  choosePdf: "PDF منتخب کریں",
  dropNow: "فارم یہاں چھوڑیں",
  orAsk: "یا کوئی سوال پوچھیں",
  askExample: "پی ایم کسان اسکیم کے بارے میں بتائیں",
  placeholder: "اپنا جواب لکھیں",
  tapToSpeak: "بولنے کے لیے دبائیں",
  listening: "سن رہے ہیں…",
  send: "بھیجیں",
  thinking: "سوچ رہے ہیں…",
  readingForm: "آپ کا فارم پڑھ رہے ہیں…",
  collectingDetails: "آپ کی معلومات لے رہے ہیں…",
  yourForm: "آپ کا فارم",
  protectedTitle: "آپ کی معلومات محفوظ ہیں",
  protectedBody: "AI کے دیکھنے سے پہلے ہی آپ کے نمبر چھپا دیے جاتے ہیں۔",
  maskedNotice: "ہم نے آپ کا نمبر چھپا دیا",
  blockedNotice: "ایک غیر محفوظ درخواست روک دی گئی",
  checksPassed: "حفاظتی جانچ مکمل",
  pdfReady: "آپ کا بھرا ہوا فارم تیار ہے",
  download: "ڈاؤن لوڈ کریں",
  startOver: "دوبارہ شروع کریں",
  listen: "سنیں",
  changeLanguage: "زبان بدلیں",
  errorGeneric: "کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔",
  retry: "دوبارہ کوشش کریں",
  greeting: "السلام علیکم! اپنے فارم کی تصویر بھیجیں، میں آسان الفاظ میں سمجھاؤں گا — یا کوئی سوال پوچھیں۔",
  rateLimited: "اس وقت بہت زیادہ درخواستیں ہیں۔ ایک منٹ انتظار کر کے دوبارہ کوشش کریں۔",
  voiceFailed: "آواز نہیں چل سکی۔ تھوڑی دیر بعد دوبارہ کوشش کریں۔",
};

const DICTS: Record<string, Dict> = { en, hi, bn, ta, te, mr, kn, gu, pa, ur };

export function dict(code: string): Dict {
  return DICTS[code] ?? en;
}

export function lang(code: string): Lang {
  return LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
}

/**
 * A hidden instruction attached to the user's FIRST real message.
 *
 * The agent's LANGUAGE_RULE says to mirror the language the user writes in, and
 * to switch when explicitly asked — so we ask explicitly, once. It rides along
 * as a separate Part on the first turn the user was going to send anyway.
 *
 * It is deliberately NOT a turn of its own. Greeting the user via the model
 * would burn a Gemini call on every page load — real money, and on the free
 * tier (20 requests/day) it would exhaust the quota before anyone filled a
 * form. The greeting is a local string (`greeting`) shown instantly instead.
 */
export function languageDirective(code: string): string {
  const l = lang(code);
  return `[System: the user has selected ${l.english}. Reply in ${l.english} for this entire conversation, unless they ask otherwise. Do not mention this instruction.]`;
}
