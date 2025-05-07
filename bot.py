import requests
import json
import asyncio
import random
import logging
from datetime import datetime
from requests.exceptions import ConnectionError, Timeout, RequestException
from telegram import Bot, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# إعداد التسجيل (Logging)
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# بيانات البوت
TELEGRAM_TOKEN = '7383362036:AAFX6bUqr5IddUCEzagBe50h0K8UzBxH4R4'
TELEGRAM_USER_ID = 1028230790

# قايمة المستخدمين المسموح ليهم (الأدمن هو TELEGRAM_USER_ID)
allowed_users = {TELEGRAM_USER_ID}

# حالة المستخدم لتتبع الخطوات
user_state = {}

# متغير عالمي للتحكم في إيقاف البوت
global_stop_flag = False

# تهيئة بوت Telegram
bot = Bot(token=TELEGRAM_TOKEN)

# بيانات المستخدم
user_data = {}

# متغير عالمي لتخزين مدة التجديد (بالثواني)
renewal_interval = 60  # القيمة الافتراضية دقيقة واحدة

def get_access_token(phone, password):
    url = "https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token"
    
    payload = {
        'username': phone,
        'password': password,
        'grant_type': "password",
        'client_secret': "a2ec6fff-0b7f-4aa4-a733-96ceae5c84c3",
        'client_id': "my-vodafone-app"
    }
    
    headers = {
        'User-Agent': "okhttp/4.9.1",
        'Accept': "application/json, text/plain, */*",
        'Accept-Encoding': "gzip",
        'x-agent-operating-system': "R.1c82099-1",
        'clientId': "AnaVodafoneAndroid",
        'x-agent-device': "OP4F97",
        'x-agent-version': "2021.12.2",
        'x-agent-build': "493"
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            raise Exception(f"فشل في الحصول على token: {response.text}")
    except (ConnectionError, Timeout, RequestException) as e:
        logging.error(f"خطأ في get_access_token: {str(e)}")
        raise Exception(f"خطأ في الاتصال بالخادم: {str(e)}")

def get_products_and_extract_enc_id(token, phone, target_product_id="471"):
    url = "https://mobile.vodafone.com.eg/services/dxl/pim/product?relatedParty.id=" + phone + "&place.@referredType=Local&@type=MIProfile"
    
    headers = {
        'User-Agent': "okhttp/4.9.1",
        'Connection': "Keep-Alive",
        'Accept': "application/json",
        'Accept-Encoding': "gzip",
        'api-host': "ProductInventoryManagementHost",
        'useCase': "MIProducts",
        'x-dynatrace': "MT_3_5_1329589472_234-0_a556db1b-4506-43f3-854a-1d2527767923_363_1573_671",
        'Authorization': f"Bearer {token}",
        'api-version': "v2",
        'x-agent-operating-system': "R.1c82099-1",
        'clientId': "AnaVodafoneAndroid",
        'x-agent-device': "OP4F97",
        'x-agent-version': "2021.12.2",
        'x-agent-build': "493",
        'Content-Type': "application/json",
        'msisdn': phone,
        'Accept-Language': "ar"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            products = response.json()
            for product in products:
                if product['id'] == target_product_id:
                    enc_product_id = product['productOffering']['encProductId']
                    return product['id'], enc_product_id
            raise Exception(f"لم يتم العثور على المنتج المطلوب (ID: {target_product_id})")
        else:
            raise Exception(f"فشل في استرداد المنتجات: {response.text}")
    except (ConnectionError, Timeout, RequestException) as e:
        logging.error(f"خطأ في get_products_and_extract_enc_id: {str(e)}")
        raise Exception(f"خطأ في الاتصال بالخادم: {str(e)}")

def activate_offer(token, product_id, enc_product_id, phone):
    url = "https://mobile.vodafone.com.eg/services/dxl/pom/productOrder"
    
    payload = {
        "channel": {
            "name": "MobileApp"
        },
        "characteristic": [],
        "orderItem": [
            {
                "action": "add",
                "product": {
                    "characteristic": [
                        {
                            "name": "LangId",
                            "value": "ar"
                        },
                        {
                            "name": "ExecutionType",
                            "value": "Sync"
                        },
                        {
                            "name": "DropAddons",
                            "value": "False"
                        },
                        {
                            "name": "MigrationType",
                            "value": "Repurchase"
                        },
                        {
                            "name": "OneStepMigrationFlag",
                            "value": "Y"
                        },
                        {
                            "name": "Journey",
                            "value": "MI_HomePage"
                        }
                    ],
                    "encProductId": enc_product_id,
                    "id": product_id,
                    "relatedParty": [
                        {
                            "id": phone,
                            "name": "MSISDN",
                            "role": "Subscriber"
                        }
                    ],
                    "@type": "MI"
                }
            }
        ],
        "@type": "MIProfile"
    }
    
    headers = {
        'User-Agent': "okhttp/4.9.1",
        'Connection': "Keep-Alive",
        'Accept': "application/json",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/json",
        'api-host': "ProductOrderingManagement",
        'useCase': "MIProfile",
        'x-dynatrace': "MT_3_5_1329589472_234-0_a556db1b-4506-43f3-854a-1d2527767923_0_1706_738",
        'Authorization': f"Bearer {token}",
        'api-version': "v2",
        'x-agent-operating-system': "R.1c82099-1",
        'clientId': "AnaVodafoneAndroid",
        'x-agent-device': "OP4F97",
        'x-agent-version': "2021.12.2",
        'x-agent-build': "493",
        'msisdn': phone,
        'Accept-Language': "ar",
        'Content-Type': "application/json; charset=UTF-8"
    }
    
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=10)
        return response.json()
    except (ConnectionError, Timeout, RequestException) as e:
        logging.error(f"خطأ في activate_offer: {str(e)}")
        raise Exception(f"خطأ في الاتصال بالخادم: {str(e)}")

# لوحة تحكم الأدمن
admin_keyboard = ReplyKeyboardMarkup([
    ["بدء", "عرض الحالة", "عرض المستخدمين"],
    ["إضافة مستخدم", "حذف مستخدم"],
    ["تعديل مدة التجديد", "إيقاف البوت", "إعادة تسجيل الدخول"],
    ["رجوع"]
], resize_keyboard=True)

async def start(update: Update, context: CallbackContext) -> None:
    """إرسال رسالة ترحيبية عند بدء البوت"""
    user_id = update.effective_user.id
    if user_id in allowed_users:
        user_state[user_id] = 'awaiting_username'
        context.user_data['is_running'] = False
        global global_stop_flag
        global_stop_flag = False
        reply_markup = admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
        await update.message.reply_text(
            "مرحباً! 👋\n\nأرسل رقم الهاتف لبدء عملية تسجيل الدخول.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("⚠️ ليس لديك صلاحية استخدام هذا البوت.")

async def stop(update: Update, context: CallbackContext) -> None:
    """إيقاف البوت"""
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        await update.message.reply_text("⚠️ ليس لديك صلاحية استخدام هذا البوت.")
        return
    global global_stop_flag
    global_stop_flag = True
    user_state.pop(user_id, None)
    context.user_data['is_running'] = False
    context.user_data.clear()
    reply_markup = admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
    await update.message.reply_text(
        "🛑 تم إيقاف البوت بنجاح. يمكنك البدء مرة أخرى باستخدام /start",
        reply_markup=reply_markup
    )

async def cancel(update: Update, context: CallbackContext) -> None:
    """إلغاء العملية"""
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        await update.message.reply_text("⚠️ ليس لديك صلاحية استخدام هذا البوت.")
        return
    global global_stop_flag
    global_stop_flag = True
    user_state.pop(user_id, None)
    context.user_data['is_running'] = False
    context.user_data.clear()
    reply_markup = admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
    await update.message.reply_text(
        "🛑 تم إلغاء العملية. يمكنك البدء مرة أخرى باستخدام /start",
        reply_markup=reply_markup
    )

async def add_user(update: Update, context: CallbackContext) -> None:
    """إضافة مستخدم جديد (للأدمن فقط)"""
    user_id = update.effective_user.id
    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للأدمن فقط.")
        return
    
    try:
        new_user_id = int(context.args[0])
        if new_user_id in allowed_users:
            await update.message.reply_text(f"المستخدم {new_user_id} موجود بالفعل.", reply_markup=admin_keyboard)
        else:
            allowed_users.add(new_user_id)
            await update.message.reply_text(f"تم إضافة المستخدم {new_user_id} بنجاح.", reply_markup=admin_keyboard)
    except (IndexError, ValueError):
        user_state[user_id] = 'adding_user'
        await update.message.reply_text("يرجى إدخال معرف المستخدم. مثال: 123456789", reply_markup=ReplyKeyboardRemove())

async def remove_user(update: Update, context: CallbackContext) -> None:
    """حذف مستخدم (للأدمن فقط)"""
    user_id = update.effective_user.id
    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للأدمن فقط.")
        return
    
    try:
        user_to_remove = int(context.args[0])
        if user_to_remove == TELEGRAM_USER_ID:
            await update.message.reply_text("لا يمكن حذف الأدمن.", reply_markup=admin_keyboard)
        elif user_to_remove in allowed_users:
            allowed_users.remove(user_to_remove)
            await update.message.reply_text(f"تم حذف المستخدم {user_to_remove} بنجاح.", reply_markup=admin_keyboard)
        else:
            await update.message.reply_text(f"المستخدم {user_to_remove} غير موجود.", reply_markup=admin_keyboard)
    except (IndexError, ValueError):
        user_state[user_id] = 'removing_user'
        await update.message.reply_text("يرجى إدخال معرف المستخدم. مثال: 123456789", reply_markup=ReplyKeyboardRemove())

async def list_users(update: Update, context: CallbackContext) -> None:
    """عرض قايمة المستخدمين (للأدمن فقط)"""
    user_id = update.effective_user.id
    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للأدمن فقط.")
        return
    
    if allowed_users:
        users_list = "\n".join([f"- {uid}" for uid in allowed_users])
        await update.message.reply_text(f"المستخدمون المسموح لهم:\n{users_list}", reply_markup=admin_keyboard)
    else:
        await update.message.reply_text("لا يوجد مستخدمون مسموح لهم.", reply_markup=admin_keyboard)

async def show_status(update: Update, context: CallbackContext) -> None:
    """عرض حالة البوت (للأدمن فقط)"""
    user_id = update.effective_user.id
    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للأدمن فقط.")
        return
    
    is_running = context.user_data.get('is_running', False)
    renewal_count = context.user_data.get('renewal_count', 0)
    status = "شغال" if is_running else "متوقف"
    await update.message.reply_text(
        f"📊 حالة البوت: {status}\n"
        f"🔄 عدد التجديدات الناجحة: {renewal_count}\n"
        f"⏳ مدة التجديد: {renewal_interval} ثانية",
        reply_markup=admin_keyboard
    )

async def set_renewal_interval(update: Update, context: CallbackContext) -> None:
    """تعديل مدة التجديد (للأدمن فقط)"""
    user_id = update.effective_user.id
    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للأدمن فقط.")
        return
    
    user_state[user_id] = 'setting_renewal_interval'
    await update.message.reply_text(
        "⏳ يرجى إدخال مدة التجديد الجديدة (بالثواني، مثال: 60 لدقيقة واحدة):",
        reply_markup=ReplyKeyboardRemove()
    )

async def re_login(update: Update, context: CallbackContext) -> None:
    """إعادة تسجيل الدخول يدويًا (للأدمن فقط)"""
    user_id = update.effective_user.id
    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للأدمن فقط.")
        return
    
    if not context.user_data.get('phone') or not context.user_data.get('password'):
        await update.message.reply_text(
            "⚠️ لا توجد بيانات تسجيل دخول محفوظة. ابدأ بـ /start",
            reply_markup=admin_keyboard
        )
        return
    
    await update.message.reply_text("⏳ جاري تسجيل الدخول مرة أخرى للحصول على توكن جديد...")
    try:
        access_token = get_access_token(context.user_data['phone'], context.user_data['password'])
        context.user_data['access_token'] = access_token
        context.user_data['renewal_count'] = 0
        await update.message.reply_text("✅ تم تسجيل الدخول بنجاح بتوكن جديد!", reply_markup=admin_keyboard)
        print("✅ تم تسجيل الدخول بنجاح بتوكن جديد!")  # عرض في الـ CMD
    except Exception as e:
        await update.message.reply_text(
            f"❌ فشل تسجيل الدخول: {str(e)}",
            reply_markup=admin_keyboard
        )
        logging.error(f"فشل إعادة تسجيل الدخول: {str(e)}")
        print(f"❌ فشل تسجيل الدخول: {str(e)}")  # عرض في الـ CMD

async def handle_message(update: Update, context: CallbackContext) -> None:
    """معالجة الرسائل الواردة من المستخدم"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in allowed_users:
        await update.message.reply_text("⚠️ ليس لديك صلاحية استخدام هذا البوت.")
        return
    
    if user_id not in user_state:
        await update.message.reply_text("يرجى البدء باستخدام الأمر /start")
        return
    
    # معالجة أوامر الأدمن من الأزرار حتى لو في حالة logged_in
    if user_id == TELEGRAM_USER_ID:
        if text == "بدء":
            if user_state[user_id] == 'logged_in' and context.user_data.get('is_running', False):
                await update.message.reply_text(
                    "⚙️ البوت يعمل بالفعل!",
                    reply_markup=admin_keyboard
                )
            else:
                await start(update, context)
            return
        elif text == "عرض الحالة":
            await show_status(update, context)
            return
        elif text == "عرض المستخدمين":
            await list_users(update, context)
            return
        elif text == "إضافة مستخدم":
            user_state[user_id] = 'adding_user'
            await update.message.reply_text(
                "يرجى إدخال معرف المستخدم. مثال: 123456789",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        elif text == "حذف مستخدم":
            user_state[user_id] = 'removing_user'
            await update.message.reply_text(
                "يرجى إدخال معرف المستخدم. مثال: 123456789",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        elif text == "تعديل مدة التجديد":
            await set_renewal_interval(update, context)
            return
        elif text == "إيقاف البوت":
            await stop(update, context)
            return
        elif text == "إعادة تسجيل الدخول":
            await re_login(update, context)
            return
        elif text == "رجوع":
            user_state[user_id] = None
            await update.message.reply_text("تم الرجوع إلى لوحة التحكم.", reply_markup=admin_keyboard)
            return
    
    # معالجة إدخال معرف مستخدم للإضافة أو الحذف
    if user_state[user_id] == 'adding_user' and user_id == TELEGRAM_USER_ID:
        try:
            new_user_id = int(text)
            if new_user_id in allowed_users:
                await update.message.reply_text(f"المستخدم {new_user_id} موجود بالفعل.", reply_markup=admin_keyboard)
            else:
                allowed_users.add(new_user_id)
                await update.message.reply_text(f"تم إضافة المستخدم {new_user_id} بنجاح.", reply_markup=admin_keyboard)
            user_state[user_id] = None
        except ValueError:
            await update.message.reply_text(
                "يرجى إدخال معرف مستخدم صحيح (أرقام فقط).",
                reply_markup=ReplyKeyboardRemove()
            )
        return
    
    if user_state[user_id] == 'removing_user' and user_id == TELEGRAM_USER_ID:
        try:
            user_to_remove = int(text)
            if user_to_remove == TELEGRAM_USER_ID:
                await update.message.reply_text("لا يمكن حذف الأدمن.", reply_markup=admin_keyboard)
            elif user_to_remove in allowed_users:
                allowed_users.remove(user_to_remove)
                await update.message.reply_text(f"تم حذف المستخدم {user_to_remove} بنجاح.", reply_markup=admin_keyboard)
            else:
                await update.message.reply_text(f"المستخدم {user_to_remove} غير موجود.", reply_markup=admin_keyboard)
            user_state[user_id] = None
        except ValueError:
            await update.message.reply_text(
                "يرجى إدخال معرف مستخدم صحيح (أرقام فقط).",
                reply_markup=ReplyKeyboardRemove()
            )
        return
    
    # معالجة إدخال مدة التجديد
    if user_state[user_id] == 'setting_renewal_interval' and user_id == TELEGRAM_USER_ID:
        try:
            new_interval = int(text)
            if new_interval < 10:
                await update.message.reply_text(
                    "⚠️ المدة يجب أن تكون 10 ثوانٍ على الأقل.",
                    reply_markup=admin_keyboard
                )
            else:
                global renewal_interval
                renewal_interval = new_interval
                await update.message.reply_text(
                    f"✅ تم تعديل مدة التجديد إلى {new_interval} ثانية.",
                    reply_markup=admin_keyboard
                )
                user_state[user_id] = None
        except ValueError:
            await update.message.reply_text(
                "يرجى إدخال مدة صحيحة (أرقام فقط، بالثواني).",
                reply_markup=ReplyKeyboardRemove()
            )
        return
    
    # معالجة إدخال رقم الهاتف وكلمة المرور
    if user_state[user_id] == 'awaiting_username':
        phone = text
        if not phone.isdigit() or len(phone) != 11 or not phone.startswith('01'):
            await update.message.reply_text(
                'رقم الهاتف غير صحيح. الرجاء إدخال رقم هاتف صحيح (11 رقماً تبدأ بـ 01)'
            )
            return
        context.user_data['phone'] = phone
        user_state[user_id] = 'awaiting_password'
        await update.message.reply_text(
            "📝 حسنًا، الآن أرسل كلمة المرور:",
            reply_markup=ReplyKeyboardRemove()
        )
    elif user_state[user_id] == 'awaiting_password':
        context.user_data['password'] = text
        user_state[user_id] = 'processing'
        
        phone = context.user_data['phone']
        password = context.user_data['password']
        
        await update.message.reply_text("⏳ جاري محاولة تسجيل الدخول...")
        
        try:
            access_token = get_access_token(phone, password)
            if access_token:
                await update.message.reply_text(
                    "✅ تم تسجيل الدخول بنجاح!",
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                context.user_data['access_token'] = access_token
                context.user_data['msisdn'] = phone
                context.user_data['renewal_count'] = 0
                context.user_data['is_running'] = True
                user_state[user_id] = 'logged_in'
                await start_creating_orders(update, context)
            else:
                await update.message.reply_text(
                    "❌ فشل تسجيل الدخول، يرجى المحاولة مرة أخرى باستخدام /start",
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                user_state.pop(user_id, None)
        except Exception as e:
            await update.message.reply_text(
                f"❌ حدث خطأ أثناء تسجيل الدخول:\n{str(e)}",
                reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
            )
            logging.error(f"خطأ أثناء تسجيل الدخول: {str(e)}")
            user_state.pop(user_id, None)
    else:
        await update.message.reply_text(
            "⚙️ البوت مشغول حاليًا، جرب استخدام الأزرار أو الأوامر.",
            reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
        )

async def start_creating_orders(update: Update, context: CallbackContext) -> None:
    """بدء عملية إنشاء طلبات المنتج"""
    user_id = update.effective_user.id
    if user_id not in user_state or user_state[user_id] != 'logged_in':
        return
    
    await update.message.reply_text(
        "🚀 بدء عملية إنشاء طلبات المنتج...",
        reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
    )
    
    access_token = context.user_data['access_token']
    msisdn = context.user_data['msisdn']
    phone = context.user_data['phone']
    password = context.user_data['password']
    
    global global_stop_flag
    while user_state.get(user_id) == 'logged_in' and context.user_data.get('is_running', False) and not global_stop_flag:
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await update.message.reply_text(
                f"⏰ محاولة الحصول على العرض في: {current_time}",
                reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
            )
            print(f"⏰ محاولة الحصول على العرض في: {current_time}")  # عرض في الـ CMD
            
            product_id, enc_product_id = get_products_and_extract_enc_id(access_token, msisdn)
            await update.message.reply_text(
                f"تم العثور على العرض: {product_id}",
                reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
            )
            
            order_response = activate_offer(access_token, product_id, enc_product_id, msisdn)
            
            if order_response.get('status') == 'Success':
                context.user_data['renewal_count'] += 1
                result = json.dumps(order_response, indent=4, ensure_ascii=False)
                await update.message.reply_text(
                    f"✅ تم إنشاء طلب المنتج بنجاح:\n\n{result}",
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                print("✅ تم إنشاء طلب المنتج بنجاح")  # عرض في الـ CMD
            elif order_response.get('statusCode') == 555:
                error_msg = "🚫انت محظور مؤقتا\n❌ خطأ في إنشاء طلب المنتج: 555\n\n" + json.dumps(order_response, ensure_ascii=False)
                await update.message.reply_text(
                    error_msg,
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                print(error_msg)  # عرض في الـ CMD
            elif order_response.get('statusCode') == 400 or (order_response.get('code') == '2252' and order_response.get('reason') == 'Insufficient balance'):
                context.user_data['renewal_count'] += 1
                await update.message.reply_text(
                    "🎉 تم تجديد النت بنجاح ✨",
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                print("🎉 تم تجديد النت بنجاح ✨")  # عرض في الـ CMD
            else:
                error_msg = f"❌ خطأ في إنشاء طلب المنتج: {order_response.get('statusCode', 'غير معروف')}\n\n{json.dumps(order_response, ensure_ascii=False)}"
                await update.message.reply_text(
                    error_msg,
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                print(error_msg)  # عرض في الـ CMD
                logging.error(f"خطأ في إنشاء طلب المنتج: {error_msg}")
            
            if context.user_data['renewal_count'] >= 5:
                await update.message.reply_text(
                    "⏳ جاري تسجيل الدخول مرة أخرى للحصول على توكن جديد...",
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                try:
                    access_token = get_access_token(phone, password)
                    context.user_data['access_token'] = access_token
                    context.user_data['renewal_count'] = 0
                    await update.message.reply_text(
                        "✅ تم تسجيل الدخول بنجاح بتوكن جديد!",
                        reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                    )
                    print("✅ تم تسجيل الدخول بنجاح بتوكن جديد!")  # عرض في الـ CMD
                except Exception as e:
                    error_msg = f"❌ فشل تسجيل الدخول: {str(e)}\nجاري إعادة المحاولة بعد دقيقتين..."
                    await update.message.reply_text(
                        error_msg,
                        reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                    )
                    print(error_msg)  # عرض في الـ CMD
                    logging.error(f"فشل تسجيل الدخول: {str(e)}")
                    for _ in range(24):  # انتظار 2 دقيقة مقسمة لـ 5 ثواني
                        if not context.user_data.get('is_running', False) or user_state.get(user_id) != 'logged_in' or global_stop_flag:
                            return
                        await asyncio.sleep(5)
                    continue
            
            await update.message.reply_text(
                f"⏳ انتظار {renewal_interval} ثانية للمحاولة التالية...",
                reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
            )
            print(f"⏳ انتظار {renewal_interval} ثانية للمحاولة التالية...")  # عرض في الـ CMD
            for _ in range(int(renewal_interval / 5)):  # تقسيم المدة لفترات 5 ثواني
                if not context.user_data.get('is_running', False) or user_state.get(user_id) != 'logged_in' or global_stop_flag:
                    return
                await asyncio.sleep(5 + random.uniform(0, 1))  # تأخير مع jitter
        except Exception as e:
            error_msg = f"⚠️ حدث خطأ: {str(e)}"
            await update.message.reply_text(
                error_msg,
                reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
            )
            print(error_msg)  # عرض في الـ CMD
            logging.error(f"خطأ في start_creating_orders: {str(e)}")
            
            # إعادة تسجيل الدخول لو الخطأ مرتبط بالتوكن
            if "token" in str(e).lower() or "authorization" in str(e).lower():
                await update.message.reply_text(
                    "⏳ جاري محاولة تسجيل الدخول مرة أخرى بسبب مشكلة في التوكن...",
                    reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                )
                try:
                    access_token = get_access_token(phone, password)
                    context.user_data['access_token'] = access_token
                    await update.message.reply_text(
                        "✅ تم تسجيل الدخول بنجاح بتوكن جديد!",
                        reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                    )
                    print("✅ تم تسجيل الدخول بنجاح بتوكن جديد!")  # عرض في الـ CMD
                    continue
                except Exception as login_e:
                    error_msg = f"❌ فشل تسجيل الدخول: {str(login_e)}\nجاري إعادة المحاولة بعد دقيقتين..."
                    await update.message.reply_text(
                        error_msg,
                        reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
                    )
                    print(error_msg)  # عرض في الـ CMD
                    logging.error(f"فشل تسجيل الدخول: {str(login_e)}")
            
            await update.message.reply_text(
                "⏳ إعادة المحاولة بعد دقيقتين...",
                reply_markup=admin_keyboard if user_id == TELEGRAM_USER_ID else ReplyKeyboardRemove()
            )
            print("⏳ إعادة المحاولة بعد دقيقتين...")  # عرض في الـ CMD
            for _ in range(24):  # انتظار 2 دقيقة مقسمة لـ 5 ثواني
                if not context.user_data.get('is_running', False) or user_state.get(user_id) != 'logged_in' or global_stop_flag:
                    return
                await asyncio.sleep(5 + random.uniform(0, 1))  # تأخير مع jitter

def main() -> None:
    """تشغيل البوت"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("adduser", add_user))
    application.add_handler(CommandHandler("removeuser", remove_user))
    application.add_handler(CommandHandler("listusers", list_users))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        application.run_polling()
    except Exception as e:
        logging.error(f"خطأ في تشغيل البوت: {str(e)}")
        print(f"خطأ في تشغيل البوت: {str(e)}")
        asyncio.sleep(120)  # إعادة المحاولة بعد دقيقتين لو البوت نفسه وقف
        main()  # إعادة تشغيل البوت

if __name__ == '__main__':
    main()