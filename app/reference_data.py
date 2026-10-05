"""Static choice lists used by forms and validation."""

PURPOSES = [
    ("network_validation", "Network and connectivity validation"),
    ("site_integration", "Site integration and UAT sign-off"),
    ("change_verification", "Post-change verification"),
    ("it_support", "IT support and troubleshooting"),
    ("qa_testing", "QA and testing"),
    ("evaluation", "Evaluating VRIOSCU"),
    ("other", "Other"),
]

FEEDBACK_CATEGORIES = [
    ("bug", "Something isn't working"),
    ("usability", "Hard to use or unclear"),
    ("report", "Report output and formatting"),
    ("feature", "Feature request"),
    ("other", "Other"),
]

SUPPORT_TOPICS = [
    ("installation", "Download and installation"),
    ("account", "Website account"),
    ("reports", "Validation runs and reports"),
    ("privacy", "Privacy or data request"),
    ("general", "General question"),
]

#COUNTRIES = [
#    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina", "Armenia", "Australia",
#    "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium",
#    "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei",
#    "Bulgaria", "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada",
#]

COUNTRIES = [

"Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina", "Armenia", "Australia", "Austria",
"Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", 
"Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso",
"Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile", 
"China", "Colombia", "Comoros", "Congo", "Costa Rica", "Côte d'Ivoire", "Croatia", "Cuba", "Cyprus", 
"Czechia", "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica", "Dominican Republic", 
"Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia",
"Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada",
"Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hong Kong", "Hungary",
"Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan",
"Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", 
"Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Malta", "Marshall Islands", "Mauritania" "Maur",
"Luxembourg", "Macao", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Monaco", "Mongolia", 
"Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Mauritius", "Mexico", "Micronesia", 
"Moldova", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", 
"Norway", "Oman", "Pakistan", "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", 
"Poland", "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
"Saint Vincent and the Grenadines", "Samoa", "San Marino", "São", "Seychelles", "Sierra Leone", "Singapore", 
"Slovakia", "Slovenia", "Solomon Islands" "São Tomé and Príncipe", "Saudi Arabia", "Senegal", "Serbia", "South Africa",
"South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Somalia", "Sweden", "Switzerland", "Syria", 
"Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", 
"Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan", 
"Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]

def label_for(choices, key):
     return dict(choices).get(key, key)