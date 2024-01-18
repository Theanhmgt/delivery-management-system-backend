import json
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, generics, permissions, parsers, status
from .models import *
from .perms import JobOwner
from .serializers import *
from rest_framework.decorators import action
from rest_framework.views import Response
from django.core.cache import cache
import cloudinary.uploader
from datetime import datetime


# Create your views here.
class UserViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView, generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    parser_classes = [parsers.MultiPartParser, ]

    @action(methods=['get', 'put'], detail=False, url_path='current-user')
    def current_user(self, request):
        u = request.user
        if request.method.__eq__('PUT'):
            for k, v in request.data.items():
                setattr(u, k, v)
            u.save()

        return Response(UserSerializer(u, context={'request': request}).data)

    @action(methods=['post'], detail=True, url_path='sent-otp')
    def sent_otp(self, request, pk):
        user = request.user
        if cache.get(user.email):
            pass
            # send email
            return Response({'opt already sent'}, status=status.HTTP_200_OK)
        else:
            return Response({'otp time is expired'}, status=status.HTTP_204_NO_CONTENT)

    @action(methods=['post'], detail=True, url_path='verify-email')
    def verify_email(self, request, pk):
        user = request.user
        opt = request.data
        cache_opt = cache.get(user.email)
        if cache_opt:
            if cache_opt == opt:
                setattr(user, 'verified', True)
            else:
                return Response({'incorrect otp'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'opt already sent'}, status=status.HTTP_200_OK)
        else:
            return Response({'otp time is expired'}, status=status.HTTP_204_NO_CONTENT)


class ShipperViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView, generics.CreateAPIView):
    queryset = Shipper.objects.all()
    serializer_class = ShipperSerializer
    parser_classes = [parsers.MultiPartParser, ]


class RoleViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView, generics.CreateAPIView):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer


class VehicleViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer


class VehicleShipperViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = VehicleShipper.objects.all()
    serializer_class = VehicleShipperSerializer


class ProductViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    parser_classes = [parsers.MultiPartParser, ]


class ProductCategoryViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class JobViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer

    def get_permissions(self):
        if self.action in ['create', 'jobs', 'my_jobs', 'post_job']:
            return [permissions.IsAuthenticated()]
        if self.action in ['my_jobs', 'accept']:
            return [JobOwner()]
        return [permissions.AllowAny()]

    @action(methods=['post'], detail=False)
    @transaction.atomic()
    def post_job(self, request):
        try:
            job_data = json.loads(request.data.get('job'))
            upload_result = cloudinary.uploader.upload(request.data.get('image'), folder='job_image')
            job_data['image'] = upload_result['url']

            products_data = json.loads(request.data.get('products'))
            shipment_data = json.loads(request.data.get('shipment'))

            user = request.user
            job_data['poster'] = user.id

            with transaction.atomic():
                job = JobSerializer(data=job_data, )
                job.is_valid(raise_exception=True)
                job_instance = job.save()
                products = []

                with transaction.atomic():
                    for product in products_data:
                        product['job'] = job_instance.id
                        p = ProductSerializer(data=product)
                        p.is_valid(raise_exception=True)
                        p.save()
                        products.append(p.data)

                with transaction.atomic():
                    pick_up_data = shipment_data['pick_up']
                    delivery_address_data = shipment_data['delivery_address']

                    pick_up = AddressSerializer(data=pick_up_data)
                    pick_up.is_valid(raise_exception=True)
                    pick_up.save()

                    delivery_address = AddressSerializer(data=delivery_address_data)
                    delivery_address.is_valid(raise_exception=True)
                    delivery_address.save()

                    shipment_data['delivery_address'] = delivery_address.data['id']
                    shipment_data['pick_up'] = pick_up.data['id']
                    shipment_data['job'] = job.data['id']

                    shipment = ShipmentSerializer(data=shipment_data)
                    shipment.is_valid(raise_exception=True)

                    shipment_responce = {**shipment.data, 'delivery_address': {**delivery_address.data},
                                         'pick_up': {**pick_up.data}}

                responce_data = {
                    'job': {**job.data},
                    'products': products,
                    'shipment': {**shipment_responce}
                }
            return Response(json.dumps(responce_data), status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"Error in outer function: {e}")
            return Response(e, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=False)
    def jobs(self, request):
        fromDate = request.query_params.get('fromDate')
        toDate = request.query_params.get('toDate')
        jobs_query = None
        if fromDate and toDate:
            fD = datetime.strptime(fromDate, '%d/%m/%Y')
            tD = datetime.strptime(toDate, '%d/%m/%Y')
            jobs_query = Job.objects.filter(is_active=True, shipment_job__shipping_date__gte=fD,
                                            shipment_job__expected_delivery_date__lte=tD).prefetch_related(
                'shipment_job', 'product_job')
        else:
            jobs_query = Job.objects.filter(is_active=True).prefetch_related('shipment_job', 'product_job')
        jobs_data = JobSerializer(jobs_query, many=True).data

        for i in range(len(jobs_data)):
            shipment = [shipment for shipment in
                        jobs_query[i].shipment_job.all().select_related('pick_up', 'delivery_address')]
            jobs_data[i]['shipment'] = ShipmentSerializer(shipment[0]).data
            products = [products for products in jobs_query[i].product_job.all()]
            jobs_data[i]['products'] = ProductSerializer(products, many=True).data
        return HttpResponse(json.dumps(jobs_data), status=status.HTTP_200_OK)

    @action(methods=['get'], detail=False)
    def my_jobs(self, request):
        user = request.user
        jobs_query = Job.objects.filter(is_active=True, poster_id=user.id).prefetch_related('shipment_job',
                                                                                            'product_job',
                                                                                            'auction_job')
        jobs_data = JobSerializer(jobs_query, many=True).data
        for i in range(len(jobs_data)):
            shipment = [shipment for shipment in
                        jobs_query[i].shipment_job.all().select_related('pick_up', 'delivery_address')]
            jobs_data[i]['shipment'] = ShipmentSerializer(shipment[0]).data

            products = [products for products in jobs_query[i].product_job.all()]
            jobs_data[i]['products'] = ProductSerializer(products, many=True).data

            auctions = [auction for auction in jobs_query[i].auction_job.all().select_related('shipper')]
            jobs_data[i]['auctions'] = AuctionSerializer(auctions, many=True).data
        return HttpResponse(json.dumps(jobs_data), status=status.HTTP_200_OK)
        # return Response({'data'}, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False)
    def accept(self, request):
        job_id = request.data.get('job')
        shipper_id = request.data.get('shipper')
        user = request.user
        if job_id and shipper_id:
            try:
                job = Job.objects.get(pk=int(job_id), poster_id=user.id)
                shipper = Shipper.objects.get(pk=int(shipper_id))
                job.winner = shipper
                job.save()
                return Response(status=status.HTTP_200_OK)
            except Job.DoesNotExist:
                return Response({'Poster not found'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class ShipmentViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer


class AddressViewSet(viewsets.ViewSet, viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
