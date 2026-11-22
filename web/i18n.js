window.I18N = {
  en: { join: 'Join Proofgrain', your_name: 'Your name', village: 'Village / mandi', farmer: 'Farmer', buyer: 'Buyer',
        assessor: 'Assessor', start: 'Start', logout: 'Log out', new_batch: 'New batch', rice: 'Rice', wheat: 'Wheat',
        create: 'Create', my_batches: 'My batches', crop: 'Crop', grade: 'Grade', grade_batch: 'Grade batch',
        photo_hint: 'Spread 100+ grains on the blue mat, place the colour card in the top-left box, take a photo from above.',
        use_sample: 'Use a sample photo', market: 'Market', disputes: 'Disputes', ledger: 'Tamper-evident ledger',
        verify: 'Verify whole chain', list_it: 'List for sale', suggested: 'Suggested price', bid: 'Bid', accept: 'Accept',
        history: 'History', dispute: 'Dispute' },
  hi: { join: 'प्रूफग्रेन से जुड़ें', your_name: 'आपका नाम', village: 'गाँव / मंडी', farmer: 'किसान', buyer: 'खरीदार',
        assessor: 'जाँचकर्ता', start: 'शुरू करें', logout: 'लॉग आउट', new_batch: 'नया लॉट', rice: 'चावल', wheat: 'गेहूँ',
        create: 'बनाएँ', my_batches: 'मेरे लॉट', crop: 'फसल', grade: 'ग्रेड', grade_batch: 'लॉट की ग्रेडिंग',
        photo_hint: 'नीली चटाई पर 100+ दाने फैलाएँ, रंग कार्ड ऊपर-बाएँ बॉक्स में रखें, ऊपर से फोटो लें।',
        use_sample: 'नमूना फोटो लें', market: 'बाज़ार', disputes: 'विवाद', ledger: 'छेड़छाड़-रोधी बही',
        verify: 'पूरी श्रृंखला जाँचें', list_it: 'बिक्री के लिए डालें', suggested: 'सुझाया भाव', bid: 'बोली', accept: 'स्वीकारें',
        history: 'इतिहास', dispute: 'विवाद' },
  mr: { join: 'प्रूफग्रेनमध्ये सामील व्हा', your_name: 'तुमचे नाव', village: 'गाव / बाजार', farmer: 'शेतकरी', buyer: 'खरेदीदार',
        assessor: 'तपासनीस', start: 'सुरू करा', logout: 'बाहेर पडा', new_batch: 'नवीन लॉट', rice: 'तांदूळ', wheat: 'गहू',
        create: 'तयार करा', my_batches: 'माझे लॉट', crop: 'पीक', grade: 'दर्जा', grade_batch: 'लॉटचा दर्जा',
        photo_hint: 'निळ्या चटईवर 100+ दाणे पसरा, रंग कार्ड वर-डाव्या चौकटीत ठेवा, वरून फोटो घ्या.',
        use_sample: 'नमुना फोटो वापरा', market: 'बाजार', disputes: 'वाद', ledger: 'फेरफार-रोधी खातेवही',
        verify: 'संपूर्ण साखळी तपासा', list_it: 'विक्रीसाठी ठेवा', suggested: 'सुचवलेला भाव', bid: 'बोली', accept: 'स्वीकारा',
        history: 'इतिहास', dispute: 'वाद' },
};
window.t = k => (I18N[localStorage.getItem('pg_lang') || 'en'] || I18N.en)[k] || I18N.en[k] || k;
window.applyI18n = () => {
  document.querySelectorAll('[data-t]').forEach(e => e.textContent = t(e.dataset.t));
  document.querySelectorAll('[data-tp]').forEach(e => e.placeholder = t(e.dataset.tp));
};
