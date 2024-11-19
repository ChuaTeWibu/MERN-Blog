from django.shortcuts import render
from django.http import JsonResponse
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.db.models import Sum
# Restframework
from rest_framework import status
from rest_framework.decorators import api_view, APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound, ValidationError

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from datetime import datetime

# Others
import json
import random

# Custom Imports
from api import serializer as api_serializer
from api import models as api_models

import logging
logger = logging.getLogger(__name__)

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = api_serializer.MyTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    queryset = api_models.User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.RegisterSerializer

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                error_messages = {
                    'email': "Email này đã được sử dụng",
                    'password': "Mật khẩu không hợp lệ"
                }
                
                for field, errors in serializer.errors.items():
                    if field in error_messages:
                        if field == 'password' and "Mật khẩu không khớp" in str(errors[0]):
                            return Response(
                                {"error": "Mật khẩu không khớp"},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        return Response(
                            {"error": error_messages[field]},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            self.perform_create(serializer)
            return Response(
                {"message": "Đăng ký thành công"},
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Error in RegisterView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi đăng ký"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.ProfileSerializer

    def get_object(self):
        try:
            user_id = self.kwargs['user_id']
            user = api_models.User.objects.get(id=user_id)
            profile = api_models.Profile.objects.get(user=user)
            return profile
        except (api_models.User.DoesNotExist, api_models.Profile.DoesNotExist) as e:
            logger.error(f"Error in ProfileView: {str(e)}")
            raise NotFound(detail="Không tìm thấy hồ sơ người dùng")

######################## Post APIs ########################

class CategoryListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.CategorySerializer
    permission_classes = [AllowAny]
    queryset = api_models.Category.objects.all()

class PostCategoryListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        try:
            category_slug = self.kwargs['category_slug']
            category = api_models.Category.objects.get(slug=category_slug)
            return api_models.Post.objects.filter(category=category, status="Active")
        except api_models.Category.DoesNotExist:
            logger.error(f"Category not found with slug: {category_slug}")
            raise NotFound(detail="Không tìm thấy danh mục này")
        except Exception as e:
            logger.error(f"Error in PostCategoryListAPIView: {str(e)}")
            return []

class PostListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]
    queryset = api_models.Post.objects.all()
    
class PostDetailAPIView(generics.RetrieveAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        try:
            slug = self.kwargs['slug']
            logger.debug(f"Trying to fetch post with slug: {slug}")
            post = api_models.Post.objects.get(slug=slug, status="Active")
            post.views += 1
            post.save()
            return post
        except api_models.Post.DoesNotExist:
            logger.warning(f"Post not found with slug: {slug}")
            raise NotFound(detail="Không tìm thấy bài viết này")
        except Exception as e:
            logger.error(f"Error in PostDetailAPIView: {str(e)}")
            raise NotFound(detail="Đã xảy ra lỗi khi tải bài viết")
        
class LikePostAPIView(APIView):
    def post(self, request):
        try:
            post_id = request.data.get('post_id')
            if not post_id:
                return Response(
                    {"error": "post_id là bắt buộc"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                post = api_models.Post.objects.get(id=post_id)
            except api_models.Post.DoesNotExist:
                return Response(
                    {"error": "Không tìm thấy bài viết"}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            if request.user in post.likes.all():
                post.likes.remove(request.user)
                liked = False
            else:
                post.likes.add(request.user)
                liked = True

            return Response({
                'status': 'success',
                'liked': liked,
                'likes_count': post.likes.count()
            })

        except Exception as e:
            logger.error(f"Error in LikePostAPIView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi thích bài viết"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PostCommentAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'post_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'name': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'comment': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        try:
            post_id = request.data['post_id']
            name = request.data['name']
            email = request.data['email']
            comment = request.data['comment']

            post = api_models.Post.objects.get(id=post_id)

            api_models.Comment.objects.create(
                post=post,
                name=name,
                email=email,
                comment=comment,
            )

            api_models.Notification.objects.create(
                user=post.user,
                post=post,
                type="Comment",
            )

            return Response({"message": "Commented Sent"}, status=status.HTTP_201_CREATED)
        except api_models.Post.DoesNotExist:
            return Response(
                {"error": "Không tìm thấy bài viết"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in PostCommentAPIView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi gửi bình luận"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
 
class BookmarkPostAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'post_id': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    
    def post(self, request):
        try:
            user_id = request.data['user_id']
            post_id = request.data['post_id']

            user = api_models.User.objects.get(id=user_id)
            post = api_models.Post.objects.get(id=post_id)

            bookmark = api_models.Bookmark.objects.filter(post=post, user=user).first()
            if bookmark:
                bookmark.delete()
                return Response({"message": "Post Un-Bookmarked"}, status=status.HTTP_200_OK)
            else:
                api_models.Bookmark.objects.create(
                    user=user,
                    post=post
                )

                api_models.Notification.objects.create(
                    user=post.user,
                    post=post,
                    type="Bookmark",
                )
                return Response({"message": "Post Bookmarked"}, status=status.HTTP_201_CREATED)
        except (api_models.User.DoesNotExist, api_models.Post.DoesNotExist):
            return Response(
                {"error": "Không tìm thấy người dùng hoặc bài viết"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in BookmarkPostAPIView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi đánh dấu bài viết"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


######################## Author Dashboard APIs ########################
class DashboardStats(generics.ListAPIView):
    serializer_class = api_serializer.AuthorStats
    permission_classes = [AllowAny]

    def get_queryset(self):
        try:
            user_id = self.kwargs['user_id']
            user = api_models.User.objects.get(id=user_id)

            views = api_models.Post.objects.filter(user=user).aggregate(view=Sum("view"))['view']
            posts = api_models.Post.objects.filter(user=user).count()
            likes = api_models.Post.objects.filter(user=user).aggregate(total_likes=Sum("likes"))['total_likes']
            bookmarks = api_models.Bookmark.objects.all().count()

            return [{
                "views": views,
                "posts": posts,
                "likes": likes,
                "bookmarks": bookmarks,
            }]
        except api_models.User.DoesNotExist:
            logger.error(f"User not found with id: {user_id}")
            return []
        except Exception as e:
            logger.error(f"Error in DashboardStats: {str(e)}")
            return []
    
    def list(self, request, *args, **kwargs):
        try:
            querset = self.get_queryset()
            serializer = self.get_serializer(querset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in DashboardStats list: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi tải thống kê"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DashboardPostLists(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        try:
            user_id = self.kwargs['user_id']
            user = api_models.User.objects.get(id=user_id)
            return api_models.Post.objects.filter(user=user).order_by("-id")
        except api_models.User.DoesNotExist:
            logger.error(f"User not found with id: {user_id}")
            return []
        except Exception as e:
            logger.error(f"Error in DashboardPostLists: {str(e)}")
            return []

class DashboardCommentLists(generics.ListAPIView):
    serializer_class = api_serializer.CommentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        try:
            return api_models.Comment.objects.all()
        except Exception as e:
            logger.error(f"Error in DashboardCommentLists: {str(e)}")
            return []

class DashboardNotificationLists(generics.ListAPIView):
    serializer_class = api_serializer.NotificationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        try:
            user_id = self.kwargs['user_id']
            user = api_models.User.objects.get(id=user_id)
            return api_models.Notification.objects.filter(seen=False, user=user)
        except api_models.User.DoesNotExist:
            logger.error(f"User not found with id: {user_id}")
            return []
        except Exception as e:
            logger.error(f"Error in DashboardNotificationLists: {str(e)}")
            return []

class DashboardMarkNotiSeenAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'noti_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            },
        ),
    )
    def post(self, request):
        try:
            noti_id = request.data['noti_id']
            noti = api_models.Notification.objects.get(id=noti_id)

            noti.seen = True
            noti.save()

            return Response({"message": "Noti Marked As Seen"}, status=status.HTTP_200_OK)
        except api_models.Notification.DoesNotExist:
            return Response(
                {"error": "Không tìm thấy thông báo"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in DashboardMarkNotiSeenAPIView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi đnh dấu thông báo"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DashboardPostCommentAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'comment_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'reply': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        try:
            comment_id = request.data['comment_id']
            reply = request.data['reply']

            comment = api_models.Comment.objects.get(id=comment_id)
            comment.reply = reply
            comment.save()

            return Response({"message": "Comment Response Sent"}, status=status.HTTP_201_CREATED)
        except api_models.Comment.DoesNotExist:
            return Response(
                {"error": "Không tìm thấy bình luận"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in DashboardPostCommentAPIView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi trả lời bình luận"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
class DashboardPostCreateAPIView(generics.CreateAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        try:
            user_id = request.data.get('user_id')
            title = request.data.get('title')
            image = request.data.get('image')
            description = request.data.get('description')
            tags = request.data.get('tags')
            category_id = request.data.get('category')
            post_status = request.data.get('post_status')

            user = api_models.User.objects.get(id=user_id)
            category = api_models.Category.objects.get(id=category_id)

            post = api_models.Post.objects.create(
                user=user,
                title=title,
                image=image,
                description=description,
                tags=tags,
                category=category,
                status=post_status
            )

            return Response({"message": "Post Created Successfully"}, status=status.HTTP_201_CREATED)
        except (api_models.User.DoesNotExist, api_models.Category.DoesNotExist):
            return Response(
                {"error": "Không tìm thấy người dùng hoặc danh mục"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in DashboardPostCreateAPIView: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi tạo bài viết"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DashboardPostEditAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        try:
            user_id = self.kwargs['user_id']
            post_id = self.kwargs['post_id']
            user = api_models.User.objects.get(id=user_id)
            return api_models.Post.objects.get(user=user, id=post_id)
        except (api_models.User.DoesNotExist, api_models.Post.DoesNotExist):
            raise NotFound(detail="Không tìm thấy bài viết hoặc người dùng")

    def update(self, request, *args, **kwargs):
        try:
            post_instance = self.get_object()

            title = request.data.get('title')
            image = request.data.get('image')
            description = request.data.get('description')
            tags = request.data.get('tags')
            category_id = request.data.get('category')
            post_status = request.data.get('post_status')

            category = api_models.Category.objects.get(id=category_id)

            post_instance.title = title
            if image != "undefined":
                post_instance.image = image
            post_instance.description = description
            post_instance.tags = tags
            post_instance.category = category
            post_instance.status = post_status
            post_instance.save()

            return Response({"message": "Post Updated Successfully"}, status=status.HTTP_200_OK)
        except api_models.Category.DoesNotExist:
            return Response(
                {"error": "Không tìm thấy danh mục"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in DashboardPostEditAPIView update: {str(e)}")
            return Response(
                {"error": "Đã xảy ra lỗi khi cập nhật bài viết"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )